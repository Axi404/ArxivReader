"""
arXiv 论文获取模块
解析列表页（/list/<分类>/new）拿到当天的新提交和 cross-list；一个分类一次请求，不再逐篇打开 abs 页。
只有列表页上缺标题或摘要的条目，才回退去请求 abs 页。
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .config import Config
from .listing import ListingEntry, ListingPage, parse_listing, parse_listing_date

LIST_URL = "https://arxiv.org/list/{category}/new?skip=0&show={show}"
ABS_URL = "https://arxiv.org/abs/{arxiv_id}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class ListingNotReady(Exception):
    """列表页还没更新到同一个公告日（比如几个分类的页面一新一旧）"""


@dataclass
class FetchResult:
    """一次抓取的结果：各分类的列表页"""

    listing_date: Optional[date]
    pages: Dict[str, ListingPage] = field(default_factory=dict)

    @property
    def total_entries(self) -> int:
        return sum(len(page.entries) for page in self.pages.values())


class ArxivFetcher:
    """arXiv 列表页抓取器"""

    def __init__(
        self,
        config: Config,
        get: Optional[Callable[[str], str]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._get_override = get
        self._sleep = sleep
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ---- 网络 ----

    def _get(self, url: str) -> str:
        if self._get_override is not None:
            return self._get_override(url)
        retries = max(0, self.config.misc.max_retries)
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, timeout=60)
                response.raise_for_status()
                return response.text
            except Exception as exc:  # 网络错误、5xx
                last_error = exc
                self.logger.warning(
                    f"请求失败 ({attempt + 1}/{retries + 1}) {url}: {exc}"
                )
                if attempt < retries:
                    self._sleep(min(60.0, 5.0 * (attempt + 1)))
        raise RuntimeError(f"请求失败: {url}: {last_error}")

    # ---- 列表页 ----

    def peek_listing_date(self) -> Optional[date]:
        """只看第一个分类列表页的日期（show=25，页面很小），用来判断有没有新公告"""
        category = self.config.arxiv.categories[0]
        html = self._get(LIST_URL.format(category=category, show=25))
        return parse_listing_date(html)

    def fetch_listing(self, category: str) -> ListingPage:
        html = self._get(LIST_URL.format(category=category, show=2000))
        page = parse_listing(html, category)
        if not self.config.arxiv.wants_cross_lists(category):
            page.entries = page.by_kind("new")
            page.header_counts["cross"] = None
        limit = self.config.arxiv.max_results_per_category
        new_entries = page.by_kind("new")
        if limit and limit > 0 and len(new_entries) > limit:
            # 只截新提交；被截掉的论文当天就看不到了，所以记一条警告
            self.logger.warning(
                f"{category} 有 {len(new_entries)} 篇新提交，max_results_per_category={limit}，"
                f"丢掉了 {len(new_entries) - limit} 篇；不想丢就把它设成 0"
            )
            keep = {e.arxiv_id for e in new_entries[:limit]}
            page.entries = [
                e for e in page.entries if e.kind != "new" or e.arxiv_id in keep
            ]
        shortfall = page.shortfall()
        if shortfall:
            self.logger.warning(
                f"{category} 页头数量和解析结果对不上: 页头 {page.header_counts}，"
                f"解析 {page.parsed_counts()}"
            )
        self.logger.info(
            f"{category} 列表页 {page.listing_date}: 新提交 {len(page.by_kind('new'))} 篇，"
            f"cross-list {len(page.by_kind('cross'))} 篇（页头 {page.header_counts}）"
        )
        return page

    def fetch_all(self, categories: Optional[List[str]] = None) -> FetchResult:
        """抓所有分类；各分类的列表页日期必须一致，否则抛 ListingNotReady"""
        categories = categories or self.config.arxiv.categories
        result = FetchResult(listing_date=None)
        for index, category in enumerate(categories):
            if index > 0:
                self._sleep(self.config.misc.request_delay)
            page = self.fetch_listing(category)
            if page.listing_date is None:
                raise ListingNotReady(f"{category} 列表页没有日期")
            if result.listing_date is None:
                result.listing_date = page.listing_date
            elif page.listing_date != result.listing_date:
                raise ListingNotReady(
                    f"{category} 列表页是 {page.listing_date}，"
                    f"{categories[0]} 是 {result.listing_date}"
                )
            result.pages[category] = page
        self.fill_incomplete(result)
        return result

    # ---- abs 页（只在列表页缺内容时用） ----

    def fill_incomplete(self, result: FetchResult) -> None:
        for page in result.pages.values():
            for entry in page.entries:
                if entry.complete:
                    continue
                self.logger.warning(
                    f"{entry.arxiv_id} 列表页上缺标题或摘要，改从 abs 页取"
                )
                try:
                    self._fill_from_abs(entry)
                except Exception as exc:
                    self.logger.error(f"abs 页也没取到 {entry.arxiv_id}: {exc}")
                self._sleep(self.config.misc.request_delay)

    def _fill_from_abs(self, entry: ListingEntry) -> None:
        soup = BeautifulSoup(
            self._get(ABS_URL.format(arxiv_id=entry.arxiv_id)), "html.parser"
        )

        def meta(name: str) -> List[str]:
            return [
                tag.get("content", "").strip()
                for tag in soup.find_all("meta", attrs={"name": name})
                if tag.get("content")
            ]

        titles = meta("citation_title")
        abstracts = meta("citation_abstract")
        authors = meta("citation_author")
        if titles and not entry.title:
            entry.title = titles[0]
        if abstracts and not entry.abstract:
            entry.abstract = abstracts[0]
        if authors and not entry.authors:
            entry.authors = authors

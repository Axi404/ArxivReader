"""
arXiv 论文获取模块
解析列表页（/list/<分类>/new）拿到当天的新提交和 cross-list；一个分类一次请求，不再逐篇打开 abs 页。
只有列表页上缺标题或摘要的条目，才回退去请求 abs 页。
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .config import Config
from .listing import ListingEntry, ListingPage, parse_listing, parse_listing_date
from .oai import OAI_URL, group_new_submissions, oai_set_for, parse_oai_page

LIST_URL = "https://arxiv.org/list/{category}/new?skip=0&show={show}"
ABS_URL = "https://arxiv.org/abs/{arxiv_id}"
OAI_RECORD_URL = (
    OAI_URL
    + "?verb=GetRecord&metadataPrefix=arXivRaw&identifier=oai:arXiv.org:{arxiv_id}"
)
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
    source: str = "listing"  # "listing"：列表页；"oai"：列表页卡住时从 OAI-PMH 拼的

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
        status: Optional[Callable[[str], Optional[int]]] = None,
    ):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._get_override = get
        self._status_override = status
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
            wait = min(60.0, 5.0 * (attempt + 1))
            try:
                response = self.session.get(url, timeout=120)
                if response.status_code == 503 and response.headers.get("Retry-After"):
                    # OAI-PMH 的流量控制：按它说的秒数再来
                    try:
                        wait = min(120.0, float(response.headers["Retry-After"]))
                    except ValueError:
                        pass
                response.raise_for_status()
                return response.text
            except Exception as exc:  # 网络错误、5xx
                last_error = exc
                self.logger.warning(
                    f"请求失败 ({attempt + 1}/{retries + 1}) {url}: {exc}"
                )
                if attempt < retries:
                    self._sleep(wait)
        raise RuntimeError(f"请求失败: {url}: {last_error}")

    def _status(self, url: str) -> Optional[int]:
        """只要 HTTP 状态码（200 或 404）；网络出错、别的状态码返回 None"""
        if self._status_override is not None:
            return self._status_override(url)
        for attempt in range(2):
            try:
                response = self.session.get(url, timeout=60, stream=True)
                response.close()
                if response.status_code in (200, 404):
                    return response.status_code
                self.logger.warning(f"{url} 返回 {response.status_code}")
            except Exception as exc:
                self.logger.warning(f"请求失败 {url}: {exc}")
            if attempt == 0:
                self._sleep(5.0)
        return None

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
        self._apply_limit(page)
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

    def _apply_limit(self, page: ListingPage) -> None:
        category = page.category
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

    # ---- OAI-PMH（列表页卡住时的兜底） ----

    def fetch_oai(
        self, start: date, end: Optional[date] = None, after_id: Optional[str] = None
    ) -> List[FetchResult]:
        """从 OAI-PMH 拼出 [start, end] 之间每个公告日的列表；没有新论文的日子不返回

        after_id：上一个公告日的最大编号，从它往后按编号切出每一天（见 oai.py 的 group_new_submissions）
        """
        categories = list(self.config.arxiv.categories)
        records = []
        for set_spec in sorted({oai_set_for(c) for c in categories}):
            url = (
                f"{OAI_URL}?verb=ListRecords&metadataPrefix=arXivRaw"
                f"&set={quote(set_spec, safe='')}&from={start.isoformat()}"
            )
            if end is not None:
                url += f"&until={end.isoformat()}"
            pages = 0
            while url:
                page_records, token, error = parse_oai_page(self._get(url))
                if error:
                    raise RuntimeError(f"OAI-PMH 返回错误 {error}: {url}")
                records.extend(page_records)
                pages += 1
                if not token:
                    break
                url = f"{OAI_URL}?verb=ListRecords&resumptionToken={quote(token, safe='')}"
                self._sleep(max(self.config.misc.request_delay, 3.0))
            self.logger.info(f"OAI-PMH set={set_spec} 从 {start} 起: {pages} 页")

        results: List[FetchResult] = []
        wanted = set(categories)
        for listing_date, day_records in group_new_submissions(
            records, after_id
        ).items():
            pages_by_cat: Dict[str, ListingPage] = {
                c: ListingPage(
                    category=c,
                    listing_date=listing_date,
                    header_counts={"new": None, "cross": None, "replace": None},
                    entries=[],
                )
                for c in categories
            }
            for record in day_records:
                for category in record.categories:
                    if category not in wanted:
                        continue
                    if category == record.primary_category:
                        kind = "new"
                    elif self.config.arxiv.wants_cross_lists(category):
                        kind = "cross"
                    else:
                        continue
                    pages_by_cat[category].entries.append(
                        ListingEntry(
                            arxiv_id=record.arxiv_id,
                            kind=kind,
                            title=record.title,
                            authors=list(record.authors),
                            abstract=record.abstract,
                            comments=record.comments,
                            journal_ref=record.journal_ref,
                            primary_category=record.primary_category,
                            categories=list(record.categories),
                        )
                    )
            for page in pages_by_cat.values():
                page.entries.sort(key=lambda e: (e.kind != "new", e.arxiv_id))
                self._apply_limit(page)
            result = FetchResult(
                listing_date=listing_date, pages=pages_by_cat, source="oai"
            )
            self.logger.info(
                f"OAI-PMH 拼出 {listing_date}: "
                + "，".join(
                    f"{c} 新提交 {len(p.by_kind('new'))} 篇、cross-list {len(p.by_kind('cross'))} 篇"
                    for c, p in pages_by_cat.items()
                )
            )
            results.append(result)
        return results

    def batch_max_id(self, start_id: str, max_requests: int = 30) -> Optional[str]:
        """这一批公告里最大的编号：从 start_id（已知存在）往上，按 abs 页是 200 还是 404 先倍增再二分

        编号是公告时连着分的，abs 页一公告就能打开（列表页卡住时也一样）。查不出来返回 None。
        """
        m = re.match(r"^(\d{4})\.(\d{5})$", start_id or "")
        if not m:
            return None
        prefix, low = m.group(1), int(m.group(2))
        requests_left = [max_requests]

        def exists(number: int) -> Optional[bool]:
            if number > 99999:
                return False
            if requests_left[0] <= 0:
                return None
            requests_left[0] -= 1
            code = self._status(ABS_URL.format(arxiv_id=f"{prefix}.{number:05d}"))
            self._sleep(self.config.misc.request_delay)
            return None if code is None else code == 200

        step, high = 1, None
        while high is None:
            found = exists(low + step)
            if found is None:
                return None
            if found:
                low, step = low + step, step * 2
            else:
                high = low + step
        while high - low > 1:
            middle = (low + high) // 2
            found = exists(middle)
            if found is None:
                return None
            if found:
                low = middle
            else:
                high = middle
        return f"{prefix}.{low:05d}"

    def oai_has_record(self, arxiv_id: str, day: date) -> Optional[bool]:
        """OAI-PMH 上有没有这一篇、而且 datestamp 不早于 day；出错返回 None"""
        try:
            records, _, error = parse_oai_page(
                self._get(OAI_RECORD_URL.format(arxiv_id=arxiv_id))
            )
        except Exception as exc:
            self.logger.warning(f"OAI-PMH 查 {arxiv_id} 失败: {exc}")
            return None
        if error == "idDoesNotExist":
            return False
        if error:
            self.logger.warning(f"OAI-PMH 查 {arxiv_id} 返回错误 {error}")
            return None
        return any(r.arxiv_id == arxiv_id and r.datestamp >= day for r in records)

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

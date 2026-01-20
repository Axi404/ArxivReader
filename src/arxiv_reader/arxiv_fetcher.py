"""
arXiv 论文获取模块
通过 arXiv 列表页爬取新论文
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from email.utils import parsedate_to_datetime
from typing import List, Optional, Dict, Any

import pytz
import requests
from bs4 import BeautifulSoup

from .config import Config
from .storage import PaperData, PaperStorage


@dataclass
class FetchResult:
    """论文获取结果"""
    papers_by_category: Dict[str, List[PaperData]] = field(default_factory=dict)
    is_today: bool = True  # 页面显示的日期是否是今天
    listing_date: Optional[date] = None  # 页面显示的日期
    total_papers: int = 0


class ArxivFetcher:
    """arXiv 论文获取器（爬虫模式）"""

    def __init__(self, config: Config, storage: PaperStorage):
        self.config = config
        self.storage = storage
        self.logger = logging.getLogger(__name__)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            )
        }

    def test_connection(self) -> bool:
        """测试 arXiv 列表页连通性"""
        category = self.config.arxiv.categories[0]
        html = self._fetch_list_page(category)
        return html is not None

    def _fetch_list_page(self, category: str, skip: int = 0, show: int = 2000) -> Optional[str]:
        """
        获取 arXiv 列表页

        Args:
            category: arXiv 分类代码
            skip: 跳过的条目数
            show: 每页显示数量（最大 2000）
        """
        url = f"https://arxiv.org/list/{category}/new?skip={skip}&show={show}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            self.logger.error(f"获取列表页失败 ({category}): {exc}")
            return None

    def _normalize_arxiv_id(self, raw_id: str) -> str:
        cleaned = raw_id.replace("arXiv:", "").strip()
        return re.sub(r"v\d+$", "", cleaned)

    def _extract_listing_date(self, html: str) -> Optional[date]:
        """
        从页面提取显示日期
        格式: "Showing new listings for Monday, 19 January 2026"
        """
        match = re.search(
            r"Showing new listings for \w+,\s*(\d{1,2})\s+(\w+)\s+(\d{4})",
            html
        )
        if not match:
            return None

        day, month_name, year = match.groups()
        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }
        month = month_map.get(month_name)
        if not month:
            return None

        try:
            return date(int(year), month, int(day))
        except ValueError:
            return None

    def _extract_section_counts(self, html: str) -> Dict[str, Optional[int]]:
        """
        从页面提取各部分的论文数量

        Returns:
            Dict with keys: 'new', 'cross', 'replacement'
        """
        counts: Dict[str, Optional[int]] = {
            "new": None,
            "cross": None,
            "replacement": None,
        }

        # New submissions (showing 25 of 25 entries)
        match = re.search(r"New submissions \(showing \d+ of (\d+) entries\)", html)
        if match:
            counts["new"] = int(match.group(1))

        # Cross submissions (showing 74 of 74 entries)
        match = re.search(r"Cross submissions \(showing \d+ of (\d+) entries\)", html)
        if match:
            counts["cross"] = int(match.group(1))

        # Replacement submissions (showing first 1 of 77 entries)
        match = re.search(r"Replacement submissions \(showing (?:first )?\d+ of (\d+) entries\)", html)
        if match:
            counts["replacement"] = int(match.group(1))

        return counts

    def _extract_arxiv_ids_new_only(self, html: str) -> List[str]:
        """
        只提取 New submissions 部分的论文 ID
        """
        soup = BeautifulSoup(html, "html.parser")

        # 找到 "New submissions" 标题
        new_submissions_h3 = None
        for h3 in soup.find_all("h3"):
            if "New submissions" in h3.get_text():
                new_submissions_h3 = h3
                break

        if not new_submissions_h3:
            self.logger.warning("未找到 New submissions 部分")
            return []

        # 找到 New submissions 后面的 dl 元素（包含论文列表）
        dl = new_submissions_h3.find_next("dl")
        if not dl:
            self.logger.warning("未找到 New submissions 的论文列表")
            return []

        ids = []
        for dt_tag in dl.find_all("dt"):
            abs_link = dt_tag.find("a", title="Abstract")
            if not abs_link:
                continue
            href = abs_link.get("href", "")
            if not href:
                continue
            arxiv_id = self._normalize_arxiv_id(href.split("/")[-1])
            if arxiv_id:
                ids.append(arxiv_id)

        return ids

    def _extract_meta_values(self, soup: BeautifulSoup, name: str) -> List[str]:
        values = []
        for tag in soup.find_all("meta", attrs={"name": name}):
            content = tag.get("content")
            if content:
                values.append(content.strip())
        return values

    def _extract_subject_codes(self, soup: BeautifulSoup) -> List[str]:
        subject_node = soup.find(class_="subjects")
        if not subject_node:
            return []
        text = subject_node.get_text(" ", strip=True)
        return [code.strip() for code in re.findall(r"\(([^)]+)\)", text)]

    def _extract_submission_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        meta_dates = self._extract_meta_values(soup, "citation_date")
        if meta_dates:
            try:
                return datetime.strptime(meta_dates[0], "%Y/%m/%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        history = soup.find(class_="submission-history")
        if history:
            first_line = history.get_text(" ", strip=True)
            match = re.search(r"\] (.+?) \(", first_line)
            if match:
                try:
                    parsed = parsedate_to_datetime(match.group(1))
                    return parsed.astimezone(timezone.utc)
                except Exception:
                    return None
        return None

    def _fetch_paper_details(self, arxiv_id: str, fallback_category: str) -> Optional[PaperData]:
        url = f"https://arxiv.org/abs/{arxiv_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            self.logger.error(f"获取论文详情失败 ({arxiv_id}): {exc}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        title = ""
        meta_titles = self._extract_meta_values(soup, "citation_title")
        if meta_titles:
            title = meta_titles[0]
        else:
            title_node = soup.find("h1", class_="title")
            if title_node:
                title = title_node.get_text(" ", strip=True).replace("Title:", "").strip()

        abstract = ""
        meta_abstracts = self._extract_meta_values(soup, "citation_abstract")
        if meta_abstracts:
            abstract = meta_abstracts[0]
        else:
            abstract_node = soup.find("blockquote", class_="abstract")
            if abstract_node:
                abstract = abstract_node.get_text(" ", strip=True).replace("Abstract:", "").strip()

        authors = self._extract_meta_values(soup, "citation_author")
        if not authors:
            authors_node = soup.find("div", class_="authors")
            if authors_node:
                authors = [author.get_text(strip=True) for author in authors_node.find_all("a")]

        pdf_urls = self._extract_meta_values(soup, "citation_pdf_url")
        pdf_url = pdf_urls[0] if pdf_urls else f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        categories = self._extract_subject_codes(soup)
        if not categories:
            categories = [fallback_category]

        published_dt = self._extract_submission_date(soup) or datetime.now(timezone.utc)

        return PaperData(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            abstract=abstract,
            published=published_dt.isoformat(),
            categories=categories,
            arxiv_url=url,
            pdf_url=pdf_url,
            hjfy_url=self.config.misc.hjfy_url_template.format(arxiv_id=arxiv_id),
        )

    def _load_or_fetch_paper(self, arxiv_id: str, category: str) -> Optional[PaperData]:
        existing = self.storage.load_paper(arxiv_id)
        if existing:
            return existing

        paper = self._fetch_paper_details(arxiv_id, category)
        if paper:
            self.storage.save_paper(paper)
        return paper

    def _is_listing_date_today(self, listing_date: Optional[date]) -> bool:
        """检查列表页日期是否是今天"""
        if listing_date is None:
            return False

        tz = pytz.timezone(self.config.schedule.timezone)
        today = datetime.now(tz).date()
        return listing_date == today

    def fetch_daily_papers(
        self, categories: Optional[List[str]] = None, skip_date_check: bool = False
    ) -> FetchResult:
        """
        获取每日新论文

        Args:
            categories: 要获取的类别列表，默认使用配置中的类别
            skip_date_check: 是否跳过日期检查（debug 模式）

        Returns:
            FetchResult: 包含论文和日期信息的结果对象
        """
        if categories is None:
            categories = self.config.arxiv.categories

        self.logger.info(f"开始获取每日论文，类别: {categories}，跳过日期检查: {skip_date_check}")

        result = FetchResult()
        all_papers: List[PaperData] = []

        for index, category in enumerate(categories):
            html = self._fetch_list_page(category)
            if not html:
                result.papers_by_category[category] = []
                continue

            # 检查日期（只在第一个类别检查）
            if index == 0:
                result.listing_date = self._extract_listing_date(html)
                result.is_today = self._is_listing_date_today(result.listing_date)

                if result.listing_date:
                    self.logger.info(f"arXiv 列表页日期: {result.listing_date}")
                else:
                    self.logger.warning("无法解析 arXiv 列表页日期")

                if not result.is_today and not skip_date_check:
                    tz = pytz.timezone(self.config.schedule.timezone)
                    today = datetime.now(tz).date()
                    self.logger.warning(
                        f"arXiv 列表页日期 ({result.listing_date}) 不是今天 ({today})，跳过获取"
                    )
                    return result
                elif not result.is_today and skip_date_check:
                    self.logger.info("日期不是今天，但已启用 debug 模式，继续获取")

            # 提取各部分数量并记录日志
            section_counts = self._extract_section_counts(html)
            total_count = sum(c for c in section_counts.values() if c is not None)
            self.logger.info(
                f"类别 {category} 页面统计: 总计 {total_count} 篇 "
                f"(New: {section_counts['new']}, Cross: {section_counts['cross']}, "
                f"Replacement: {section_counts['replacement']})，只获取 New submissions"
            )

            # 只提取 New submissions 部分
            arxiv_ids = self._extract_arxiv_ids_new_only(html)

            max_results = self.config.arxiv.max_results_per_category
            if max_results > 0:
                arxiv_ids = arxiv_ids[:max_results]

            papers: List[PaperData] = []
            for arxiv_id in arxiv_ids:
                paper = self._load_or_fetch_paper(arxiv_id, category)
                if paper:
                    papers.append(paper)
                time.sleep(self.config.misc.request_delay)

            result.papers_by_category[category] = papers
            all_papers.extend(papers)

            self.logger.info(f"类别 {category} 获取完成，共 {len(papers)} 篇论文")

            if index < len(categories) - 1:
                time.sleep(self.config.misc.request_delay * 2)

        result.total_papers = len(all_papers)

        if all_papers:
            self.storage.save_daily_papers(all_papers)

        self.logger.info(f"每日论文获取完成，总共 {len(all_papers)} 篇论文")
        return result

    def get_statistics(self) -> Dict[str, Any]:
        storage_stats = self.storage.get_statistics()
        return {
            "total_papers_fetched": storage_stats["total_papers"],
            "categories_configured": len(self.config.arxiv.categories),
            "max_results_per_category": self.config.arxiv.max_results_per_category,
            "request_delay": self.config.misc.request_delay,
            "storage_stats": storage_stats,
        }

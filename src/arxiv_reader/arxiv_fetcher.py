"""
arXiv 论文获取模块
通过 arXiv 列表页爬取新论文
"""

import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup

from .config import Config
from .storage import PaperData, PaperStorage


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

    def _fetch_list_page(self, category: str) -> Optional[str]:
        url = f"https://arxiv.org/list/{category}/new"
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

    def _extract_arxiv_ids(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        ids = []
        for dt_tag in soup.find_all("dt"):
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

    def fetch_daily_papers(
        self, categories: Optional[List[str]] = None
    ) -> Dict[str, List[PaperData]]:
        if categories is None:
            categories = self.config.arxiv.categories

        self.logger.info(f"开始获取每日论文，类别: {categories}")

        papers_by_category: Dict[str, List[PaperData]] = {}
        all_papers: List[PaperData] = []

        for index, category in enumerate(categories):
            html = self._fetch_list_page(category)
            if not html:
                papers_by_category[category] = []
                continue

            arxiv_ids = self._extract_arxiv_ids(html)
            max_results = self.config.arxiv.max_results_per_category
            if max_results > 0:
                arxiv_ids = arxiv_ids[:max_results]

            papers: List[PaperData] = []
            for arxiv_id in arxiv_ids:
                paper = self._load_or_fetch_paper(arxiv_id, category)
                if paper:
                    papers.append(paper)
                time.sleep(self.config.misc.request_delay)

            papers_by_category[category] = papers
            all_papers.extend(papers)

            self.logger.info(f"类别 {category} 获取完成，共 {len(papers)} 篇论文")

            if index < len(categories) - 1:
                time.sleep(self.config.misc.request_delay * 2)

        if all_papers:
            self.storage.save_daily_papers(all_papers)

        self.logger.info(f"每日论文获取完成，总共 {len(all_papers)} 篇论文")
        return papers_by_category

    def get_statistics(self) -> Dict[str, Any]:
        storage_stats = self.storage.get_statistics()
        return {
            "total_papers_fetched": storage_stats["total_papers"],
            "categories_configured": len(self.config.arxiv.categories),
            "max_results_per_category": self.config.arxiv.max_results_per_category,
            "request_delay": self.config.misc.request_delay,
            "storage_stats": storage_stats,
        }

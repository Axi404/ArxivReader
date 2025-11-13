"""
arXiv 论文获取模块
负责从 arXiv 获取指定领域的最新论文
支持 API 和 RSS 两种获取方式
"""

import logging
import time
import re
from bs4 import BeautifulSoup
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import arxiv

from .config import get_config
from .storage import PaperData, get_storage


class ArxivFetcher:
    """arXiv 论文获取器"""

    def __init__(self):
        """初始化获取器"""
        self.config = get_config()
        self.storage = get_storage()
        self.logger = logging.getLogger(__name__)

        # 根据配置选择获取方式
        self.use_rss = self.config.misc.use_rss_fetcher

        if self.use_rss:
            self.logger.info("使用 RSS 获取器")
            self.rss_base_url = self.config.misc.rss_base_url
        else:
            self.logger.info("使用 arXiv API 获取器")
            # arXiv 客户端配置
            self.client = arxiv.Client(
                page_size=300,  # 增大每页大小以减少请求次数
                delay_seconds=self.config.misc.request_delay,
                num_retries=self.config.misc.max_retries,
            )

    def fetch_arxiv_papers(
        self,
        category: str,
    ) -> List[Dict[str, str]]:
        """
        Fetch arxiv papers with ID and title

        Args:
            category: The category to fetch papers from

        Returns:
            A list of dictionaries containing arxiv_id and title
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(
                f"https://arxiv.org/list/{category}/new", headers=headers, timeout=30
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            papers = []

            # Find all paper entries
            for dt_tag in soup.find_all("dt"):
                dd_tag = dt_tag.find_next_sibling("dd")
                if dd_tag:
                    # Extract arxiv ID
                    arxiv_link = dt_tag.find("a", title="Abstract")
                    if arxiv_link:
                        arxiv_id = arxiv_link.text.strip().replace("arXiv:", "")

                        # Extract title
                        title_tag = dd_tag.find("div", class_="list-title")
                        title = (
                            title_tag.text.replace("Title:", "").strip()
                            if title_tag
                            else "N/A"
                        )

                        papers.append({"arxiv_id": arxiv_id, "title": title})

            arxiv_papers = [
                self._convert_arxiv_result_to_paper_data(
                    next(arxiv.Search(id_list=[paper["arxiv_id"]]).results())
                )
                for paper in papers
            ]
            return arxiv_papers

        except Exception as e:
            print(f"Error: {e}")
            return []

    def _get_sort_parameters(self):
        """
        获取正确的排序参数

        Returns:
            tuple: (sort_by, sort_order) arxiv 库的排序参数
        """
        # 修正排序字段名称映射
        sort_by_mapping = {
            "submittedDate": "SubmittedDate",
            "relevance": "Relevance",
            "lastUpdatedDate": "LastUpdatedDate",
        }

        sort_order_mapping = {"ascending": "Ascending", "descending": "Descending"}

        sort_by = sort_by_mapping.get(self.config.arxiv.sort_by, "SubmittedDate")
        sort_order = sort_order_mapping.get(self.config.arxiv.sort_order, "Descending")

        return (
            getattr(arxiv.SortCriterion, sort_by),
            getattr(arxiv.SortOrder, sort_order),
        )

    def _parse_arxiv_id(self, arxiv_url: str) -> str:
        """
        从 arXiv URL 中提取 ID

        Args:
            arxiv_url: arXiv URL

        Returns:
            arXiv ID
        """
        # 匹配各种可能的 arXiv URL 格式
        patterns = [
            r"arxiv\.org/abs/([0-9]+\.[0-9]+)",
            r"arxiv\.org/pdf/([0-9]+\.[0-9]+)",
            r"([0-9]+\.[0-9]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, arxiv_url)
            if match:
                return match.group(1)

        # 如果没有匹配到，返回原始 URL 的最后部分
        return arxiv_url.split("/")[-1].replace(".pdf", "")

    def _convert_arxiv_result_to_paper_data(self, result: arxiv.Result) -> PaperData:
        """
        将 arXiv 搜索结果转换为 PaperData 对象

        Args:
            result: arXiv 搜索结果

        Returns:
            PaperData 对象
        """
        # 提取 arXiv ID
        arxiv_id = self._parse_arxiv_id(result.entry_id)

        # 提取作者列表
        authors = [author.name for author in result.authors]

        categories = []
        for cat in result.categories:
            if hasattr(cat, "term"):
                categories.append(cat.term)
            else:
                categories.append(str(cat))

        # 构建 PDF URL
        pdf_url = result.pdf_url or f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        # 确保发布时间为UTC格式
        published_utc = result.published
        if published_utc.tzinfo is None:
            published_utc = published_utc.replace(tzinfo=timezone.utc)
        else:
            published_utc = published_utc.astimezone(timezone.utc)

        return PaperData(
            arxiv_id=arxiv_id,
            title=result.title.strip(),
            authors=authors,
            abstract=result.summary.strip(),
            published=published_utc.isoformat(),
            categories=categories,
            arxiv_url=result.entry_id,
            pdf_url=pdf_url,
        )

    def _fetch_rss_feed(self, category: str) -> Optional[str]:
        """
        获取指定类别的 RSS feed 内容

        Args:
            category: arXiv 类别代码

        Returns:
            RSS XML 字符串，如果获取失败返回 None
        """
        rss_url = f"{self.rss_base_url}/{category}"

        try:
            self.logger.debug(f"正在获取 RSS: {rss_url}")
            response = requests.get(rss_url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"获取 RSS feed 失败 {category}: {e}")
            return None

    def _parse_rss_item(self, item_element) -> Optional[PaperData]:
        """
        解析单个 RSS item 元素为 PaperData 对象

        Args:
            item_element: XML item 元素

        Returns:
            PaperData 对象，如果解析失败返回 None
        """
        try:
            # 定义 XML 命名空间
            ns = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "arxiv": "http://arxiv.org/schemas/atom",
            }

            # 提取基本信息
            title = (
                item_element.find("title").text.strip()
                if item_element.find("title") is not None
                else ""
            )
            link = (
                item_element.find("link").text.strip()
                if item_element.find("link") is not None
                else ""
            )
            description = (
                item_element.find("description").text
                if item_element.find("description") is not None
                else ""
            )

            # 从 description 中提取 arXiv ID 和摘要
            arxiv_id = None
            abstract = ""

            if description:
                # 提取 arXiv ID (格式如: arXiv:2509.00054v1)
                arxiv_match = re.search(r"arXiv:([0-9]+\.[0-9]+)v[0-9]+", description)
                if arxiv_match:
                    arxiv_id = arxiv_match.group(1)

                # 提取摘要 (在 "Abstract: " 之后的内容)
                abstract_match = re.search(r"Abstract:\s*(.+)", description, re.DOTALL)
                if abstract_match:
                    abstract = abstract_match.group(1).strip()

            # 如果无法从 description 中提取，使用备用方法从 link 或 guid 中提取
            if not arxiv_id:
                arxiv_id = self._parse_arxiv_id(link)

            # 提取作者
            authors = []
            creator_elem = item_element.find("dc:creator", ns)
            if creator_elem is not None and creator_elem.text:
                # 作者格式通常为 "Author1, Author2, Author3"
                authors = [
                    author.strip()
                    for author in creator_elem.text.split(",")
                    if author.strip()
                ]

            # 提取类别
            categories = []
            for cat_elem in item_element.findall("category"):
                if cat_elem.text:
                    categories.append(cat_elem.text.strip())

            # 提取发布时间
            pub_date_str = ""
            pub_date_elem = item_element.find("pubDate")
            if pub_date_elem is not None and pub_date_elem.text:
                pub_date_str = pub_date_elem.text.strip()

            # 解析发布时间
            published_utc = None
            if pub_date_str:
                try:
                    # RSS 日期格式: Wed, 03 Sep 2025 00:00:00 -0400
                    # 先移除时区信息，然后解析为 UTC
                    if pub_date_str.endswith(" -0400"):
                        pub_date_str = pub_date_str[:-6]  # 移除 " -0400"
                        dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S")
                        dt = dt.replace(
                            tzinfo=timezone(timedelta(hours=-4))
                        )  # 添加时区信息
                        published_utc = dt.astimezone(timezone.utc)
                    else:
                        # 其他格式的日期处理
                        dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                        published_utc = dt.astimezone(timezone.utc)
                except Exception as e:
                    self.logger.warning(f"解析发布时间失败: {pub_date_str}, 错误: {e}")
                    published_utc = datetime.now(timezone.utc)

            if published_utc is None:
                published_utc = datetime.now(timezone.utc)

            # 构建 PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""

            # 构建 arXiv URL
            arxiv_url = (
                link
                if link
                else f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
            )

            return PaperData(
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                abstract=abstract,
                published=published_utc.isoformat(),
                categories=categories,
                arxiv_url=arxiv_url,
                pdf_url=pdf_url,
            )

        except Exception as e:
            self.logger.error(f"解析 RSS item 失败: {e}")
            return None

    def search_papers_by_category(
        self, category: str, max_results: Optional[int] = None
    ) -> List[PaperData]:
        """
        按类别搜索论文

        Args:
            category: arXiv 类别代码 (如 'cs.AI')
            max_results: 最大结果数，如果为None则使用配置中的值

        Returns:
            论文数据列表
        """
        if max_results is None:
            max_results = self.config.arxiv.max_results_per_category

        self.logger.info(f"搜索类别 {category} 的论文，最大结果数: {max_results}")

        return self._search_papers_by_category(category, max_results)

    def _search_papers_by_category(
        self, category: str, max_results: int
    ) -> List[PaperData]:
        """
        使用 爬虫 按类别搜索论文

        Args:
            category: arXiv 类别代码
            max_results: 最大结果数

        Returns:
            论文数据列表
        """
        try:
            all_papers = self.fetch_arxiv_papers(category)

            self.logger.info(f"爬虫 获取到 {len(all_papers)} 篇论文")

            # 使用UTC时间计算日期范围
            now_utc = datetime.now(timezone.utc)
            current_weekday = now_utc.weekday()  # 0=Monday, 6=Sunday

            # 根据星期几确定搜索范围
            if current_weekday == 0:  # 星期一
                cutoff_days = 4  # 搜索到上周五
                range_desc = "上周五至今"
            elif current_weekday == 1:  # 星期二
                cutoff_days = 4  # 搜索到前天
                range_desc = "上周六至今"
            else:  # 星期三到星期日
                cutoff_days = 2  # 搜索到前天
                range_desc = "前2天至今"

            base_date = (now_utc - timedelta(days=cutoff_days)).date()
            cutoff_date = datetime(
                year=base_date.year,
                month=base_date.month,
                day=base_date.day,
                hour=18,
                minute=0,
                second=0,
                tzinfo=timezone.utc,
            )
            self.logger.info(
                f"爬虫 搜索时间范围（UTC）: {range_desc} ({cutoff_date.strftime('%Y-%m-%d')} 至今)"
            )

            # 过滤论文
            papers = []
            for paper in all_papers:
                # 解析论文发布时间并进行日期过滤
                try:
                    published_date = datetime.fromisoformat(
                        str(paper.published).replace("Z", "+00:00")
                    )
                    if published_date < cutoff_date:
                        self.logger.debug(
                            f"论文 {paper.arxiv_id} 发布时间 {published_date.strftime('%Y-%m-%d %H:%M')} 早于截止时间，跳过"
                        )
                        continue
                except (ValueError, AttributeError) as e:
                    self.logger.warning(f"解析论文 {paper.arxiv_id} 发布时间失败: {e}")
                    continue

                # 检查是否已存在，如果存在则加载已有数据（包括翻译）
                if self.storage.paper_exists(paper.arxiv_id):
                    existing_paper = self.storage.load_paper(paper.arxiv_id)
                    if existing_paper:
                        # 使用已存储的论文数据（可能包含翻译）
                        paper = existing_paper
                        self.logger.debug(f"加载已存储的论文数据: {paper.arxiv_id}")
                    else:
                        # 加载失败，保存新数据
                        self.storage.save_paper(paper)
                else:
                    # 不存在，保存新数据
                    self.storage.save_paper(paper)

                papers.append(paper)

                # 限制结果数量
                if len(papers) >= max_results:
                    break

            # 记录过滤后的论文数量
            self.logger.info(f"时间过滤后剩余 {len(papers)} 篇论文")

            # 统计从缓存加载的论文数量
            cached_count = sum(1 for p in papers if p.is_translated())
            new_count = len(papers) - cached_count

            self.logger.info(f"RSS 类别 {category} 搜索完成，找到 {len(papers)} 篇论文")
            self.logger.info(f"  - 从缓存加载: {cached_count} 篇（已翻译）")
            self.logger.info(f"  - 新获取: {new_count} 篇（需翻译）")
            return papers

        except Exception as e:
            self.logger.error(f"RSS 搜索类别 {category} 的论文时出错: {e}")
            return []

    def parse_paper_info_by_id(self, arxiv_id: str) -> Optional[str]:
        paper = next(arxiv.Search(id_list=[arxiv_id]).results())
        date = paper.published
        date = str(date).replace("Z", "+00:00")
        return date

    def fetch_daily_papers(
        self, categories: Optional[List[str]] = None
    ) -> Dict[str, List[PaperData]]:
        """
        获取每日论文

        Args:
            categories: 类别列表，如果为None则使用配置中的类别

        Returns:
            按类别分组的论文字典
        """
        if categories is None:
            categories = self.config.arxiv.categories

        self.logger.info(f"开始获取每日论文，类别: {categories}")

        papers_by_category = {}
        all_papers = []

        for category in categories:
            self.logger.info(f"正在获取类别 {category} 的论文...")

            papers = self.search_papers_by_category(category)
            papers_by_category[category] = papers
            all_papers.extend(papers)

            self.logger.info(f"类别 {category} 获取完成，共 {len(papers)} 篇论文")

            # 在类别之间添加延迟
            if category != categories[-1]:  # 不是最后一个类别
                time.sleep(self.config.misc.request_delay * 2)

        # 保存每日汇总
        if all_papers:
            self.storage.save_daily_papers(all_papers)

        self.logger.info(f"每日论文获取完成，总共 {len(all_papers)} 篇论文")
        return papers_by_category

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取获取器统计信息

        Returns:
            统计信息字典
        """
        storage_stats = self.storage.get_statistics()

        stats = {
            "total_papers_fetched": storage_stats["total_papers"],
            "categories_configured": len(self.config.arxiv.categories),
            "max_results_per_category": self.config.arxiv.max_results_per_category,
            "request_delay": self.config.misc.request_delay,
            "max_retries": self.config.misc.max_retries,
            "fetcher_type": "RSS" if self.use_rss else "API",
            "rss_base_url": self.rss_base_url if self.use_rss else None,
            "storage_stats": storage_stats,
        }

        return stats


# 全局获取器对象
_fetcher: ArxivFetcher = None


def get_fetcher() -> ArxivFetcher:
    """获取全局获取器对象"""
    global _fetcher
    if _fetcher is None:
        _fetcher = ArxivFetcher()
    return _fetcher

"""
arXiv 论文获取模块
负责从 arXiv 获取指定领域的最新论文
支持 API 和 RSS 两种获取方式
"""

import logging
import time
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import arxiv
from tqdm import tqdm

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
                'dc': 'http://purl.org/dc/elements/1.1/',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }

            # 提取基本信息
            title = item_element.find('title').text.strip() if item_element.find('title') is not None else ""
            link = item_element.find('link').text.strip() if item_element.find('link') is not None else ""
            description = item_element.find('description').text if item_element.find('description') is not None else ""

            # 从 description 中提取 arXiv ID 和摘要
            arxiv_id = None
            abstract = ""

            if description:
                # 提取 arXiv ID (格式如: arXiv:2509.00054v1)
                arxiv_match = re.search(r'arXiv:([0-9]+\.[0-9]+)v[0-9]+', description)
                if arxiv_match:
                    arxiv_id = arxiv_match.group(1)

                # 提取摘要 (在 "Abstract: " 之后的内容)
                abstract_match = re.search(r'Abstract:\s*(.+)', description, re.DOTALL)
                if abstract_match:
                    abstract = abstract_match.group(1).strip()

            # 如果无法从 description 中提取，使用备用方法从 link 或 guid 中提取
            if not arxiv_id:
                arxiv_id = self._parse_arxiv_id(link)

            # 提取作者
            authors = []
            creator_elem = item_element.find('dc:creator', ns)
            if creator_elem is not None and creator_elem.text:
                # 作者格式通常为 "Author1, Author2, Author3"
                authors = [author.strip() for author in creator_elem.text.split(',') if author.strip()]

            # 提取类别
            categories = []
            for cat_elem in item_element.findall('category'):
                if cat_elem.text:
                    categories.append(cat_elem.text.strip())

            # 提取发布时间
            pub_date_str = ""
            pub_date_elem = item_element.find('pubDate')
            if pub_date_elem is not None and pub_date_elem.text:
                pub_date_str = pub_date_elem.text.strip()

            # 解析发布时间
            published_utc = None
            if pub_date_str:
                try:
                    # RSS 日期格式: Wed, 03 Sep 2025 00:00:00 -0400
                    # 先移除时区信息，然后解析为 UTC
                    if pub_date_str.endswith(' -0400'):
                        pub_date_str = pub_date_str[:-6]  # 移除 " -0400"
                        dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S')
                        dt = dt.replace(tzinfo=timezone(timedelta(hours=-4)))  # 添加时区信息
                        published_utc = dt.astimezone(timezone.utc)
                    else:
                        # 其他格式的日期处理
                        dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
                        published_utc = dt.astimezone(timezone.utc)
                except Exception as e:
                    self.logger.warning(f"解析发布时间失败: {pub_date_str}, 错误: {e}")
                    published_utc = datetime.now(timezone.utc)

            if published_utc is None:
                published_utc = datetime.now(timezone.utc)

            # 构建 PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""

            # 构建 arXiv URL
            arxiv_url = link if link else f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""

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

    def _parse_rss_feed(self, rss_content: str) -> List[PaperData]:
        """
        解析 RSS feed 内容为论文列表

        Args:
            rss_content: RSS XML 字符串

        Returns:
            PaperData 对象列表
        """
        papers = []

        try:
            # 解析 XML
            root = ET.fromstring(rss_content)

            # 查找所有 item 元素
            for item in root.findall('.//item'):
                paper = self._parse_rss_item(item)
                if paper:
                    papers.append(paper)

        except Exception as e:
            self.logger.error(f"解析 RSS feed 失败: {e}")

        return papers

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

        if self.use_rss:
            return self._search_papers_by_category_rss(category, max_results)
        else:
            return self._search_papers_by_category_api(category, max_results)

    def _search_papers_by_category_api(
        self, category: str, max_results: int
    ) -> List[PaperData]:
        """
        使用 arXiv API 按类别搜索论文

        Args:
            category: arXiv 类别代码
            max_results: 最大结果数

        Returns:
            论文数据列表
        """
        try:
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
                tzinfo=timezone.utc
            )
            self.logger.info(f"搜索时间范围（UTC）: {range_desc} ({cutoff_date.strftime('%Y-%m-%d')} 至今)")
            # 使用类别搜索，不限制日期范围
            query = f"cat:{category}"

            # 获取正确的排序参数
            sort_by, sort_order = self._get_sort_parameters()

            # 使用传入的 max_results 参数或配置值
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            papers = []

            for result in self.client.results(search):
                paper = self._convert_arxiv_result_to_paper_data(result)

                # 使用UTC时间进行日期过滤
                try:
                    # 解析论文发布时间（转换为UTC）
                    published_date = datetime.fromisoformat(
                        paper.published.replace("Z", "+00:00")
                    )
                    if published_date.tzinfo is None:
                        published_date = published_date.replace(tzinfo=timezone.utc)
                    else:
                        published_date = published_date.astimezone(timezone.utc)
                    # 如果论文太旧，跳出循环
                    if published_date < cutoff_date:
                        self.logger.debug(f"论文 {paper.arxiv_id} 发布时间 {published_date.strftime('%Y-%m-%d %H:%M')} 早于截止时间 {cutoff_date.strftime('%Y-%m-%d %H:%M')}，停止搜索")
                        break

                except (ValueError, AttributeError) as e:
                    self.logger.warning(f"解析论文 {paper.arxiv_id} 发布时间失败: {e}")
                    continue

                if not paper.categories or category not in paper.categories:
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

                # 添加延迟以避免过于频繁的请求
                time.sleep(self.config.misc.request_delay)

            # 统计从缓存加载的论文数量
            cached_count = sum(1 for p in papers if p.is_translated())
            new_count = len(papers) - cached_count

            self.logger.info(f"类别 {category} 搜索完成，找到 {len(papers)} 篇论文")
            self.logger.info(f"  - 从缓存加载: {cached_count} 篇（已翻译）")
            self.logger.info(f"  - 新获取: {new_count} 篇（需翻译）")
            return papers

        except Exception as e:
            self.logger.error(f"搜索类别 {category} 的论文时出错: {e}")
            return []

    def _search_papers_by_category_rss(
        self, category: str, max_results: int
    ) -> List[PaperData]:
        """
        使用 RSS 按类别搜索论文

        Args:
            category: arXiv 类别代码
            max_results: 最大结果数

        Returns:
            论文数据列表
        """
        try:
            # 获取 RSS feed
            rss_content = self._fetch_rss_feed(category)
            if not rss_content:
                self.logger.warning(f"无法获取类别 {category} 的 RSS feed")
                return []

            # 解析 RSS 内容
            all_papers = self._parse_rss_feed(rss_content)
            self.logger.info(f"RSS 获取到 {len(all_papers)} 篇论文")

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
                tzinfo=timezone.utc
            )
            self.logger.info(f"RSS 搜索时间范围（UTC）: {range_desc} ({cutoff_date.strftime('%Y-%m-%d')} 至今)")

            # 过滤论文
            papers = []
            for paper in (all_papers):
                # 解析论文发布时间并进行日期过滤
                try:
                    published_date = datetime.fromisoformat(self.parse_paper_info_by_id(paper.arxiv_id))
                    if published_date < cutoff_date:
                        self.logger.debug(f"论文 {paper.arxiv_id} 发布时间 {published_date.strftime('%Y-%m-%d %H:%M')} 早于截止时间，跳过")
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
            self.logger.info(f"RSS 时间过滤后剩余 {len(papers)} 篇论文")

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

    def search_papers_by_keywords(
        self,
        keywords: List[str],
        category: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[PaperData]:
        """
        按关键词搜索论文

        Args:
            keywords: 关键词列表
            category: 可选的类别限制
            max_results: 最大结果数

        Returns:
            论文数据列表
        """
        if max_results is None:
            max_results = self.config.arxiv.max_results_per_category

        if self.use_rss:
            return self._search_papers_by_keywords_rss(keywords, category, max_results)
        else:
            return self._search_papers_by_keywords_api(keywords, category, max_results)

    def _search_papers_by_keywords_api(
        self,
        keywords: List[str],
        category: Optional[str],
        max_results: int,
    ) -> List[PaperData]:
        """
        使用 API 按关键词搜索论文

        Args:
            keywords: 关键词列表
            category: 可选的类别限制
            max_results: 最大结果数

        Returns:
            论文数据列表
        """
        # 构建关键词查询
        keyword_query = " OR ".join([f'all:"{keyword}"' for keyword in keywords])

        # 如果指定了类别，添加类别限制
        if category:
            query = f"({keyword_query}) AND cat:{category}"
        else:
            query = keyword_query

        self.logger.info(f"API 关键词搜索论文: {keywords}, 类别: {category}")

        try:
            sort_by, sort_order = self._get_sort_parameters()

            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            papers = []
            for result in self.client.results(search):
                paper = self._convert_arxiv_result_to_paper_data(result)

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

                time.sleep(self.config.misc.request_delay)

            self.logger.info(f"关键词搜索完成，找到 {len(papers)} 篇论文")
            return papers

        except Exception as e:
            self.logger.error(f"关键词搜索时出错: {e}")
            return []

    def _search_papers_by_keywords_rss(
        self,
        keywords: List[str],
        category: Optional[str],
        max_results: int,
    ) -> List[PaperData]:
        """
        使用 RSS 按关键词搜索论文

        Args:
            keywords: 关键词列表
            category: 可选的类别限制
            max_results: 最大结果数

        Returns:
            论文数据列表
        """
        self.logger.info(f"RSS 关键词搜索论文: {keywords}, 类别: {category}")

        # RSS 方式不支持关键词搜索，需要先获取类别论文，然后在本地过滤
        if not category:
            self.logger.warning("RSS 方式的关键词搜索需要指定类别")
            return []

        # 先获取类别中的论文
        all_papers = self._search_papers_by_category_rss(category, max_results * 2)  # 获取更多论文用于过滤
        self.logger.info(f"关键词搜索：获取 {len(all_papers)} 篇论文用于关键词过滤")

        # 在本地按关键词过滤
        filtered_papers = []
        keywords_lower = [kw.lower() for kw in keywords]

        for paper in all_papers:
            # 检查标题和摘要是否包含关键词
            title_lower = paper.title.lower()
            abstract_lower = paper.abstract.lower()

            if any(kw in title_lower or kw in abstract_lower for kw in keywords_lower):
                filtered_papers.append(paper)

                if len(filtered_papers) >= max_results:
                    break

        self.logger.info(f"关键词过滤后剩余 {len(filtered_papers)} 篇论文")
        self.logger.info(f"RSS 关键词搜索完成，找到 {len(filtered_papers)} 篇匹配论文")
        return filtered_papers

    def parse_paper_info_by_id(self, arxiv_id: str) -> Optional[str]:
        paper = next(arxiv.Search(id_list=[arxiv_id]).results())
        date = paper.published
        date = str(date).replace('Z', '+00:00')
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

    def get_paper_by_id(self, arxiv_id: str) -> Optional[PaperData]:
        """
        根据 arXiv ID 获取单篇论文

        Args:
            arxiv_id: arXiv ID

        Returns:
            论文数据，如果找不到则返回None
        """
        # 首先检查本地存储
        paper = self.storage.load_paper(arxiv_id)
        if paper:
            return paper

        # 如果本地没有，从 arXiv 获取
        self.logger.info(f"从 arXiv 获取论文: {arxiv_id}")

        try:
            # 单篇论文获取始终使用 API，因为 RSS 不支持按 ID 获取
            if not hasattr(self, 'client'):
                self.client = arxiv.Client(
                    page_size=300,
                    delay_seconds=self.config.misc.request_delay,
                    num_retries=self.config.misc.max_retries,
                )

            search = arxiv.Search(id_list=[arxiv_id])

            for result in self.client.results(search):
                paper = self._convert_arxiv_result_to_paper_data(result)

                # 保存到本地存储
                self.storage.save_paper(paper)

                return paper

            self.logger.warning(f"未找到论文: {arxiv_id}")
            return None

        except Exception as e:
            self.logger.error(f"获取论文 {arxiv_id} 时出错: {e}")
            return None

    def update_paper_data(self, arxiv_id: str) -> Optional[PaperData]:
        """
        更新论文数据（从 arXiv 重新获取）

        Args:
            arxiv_id: arXiv ID

        Returns:
            更新后的论文数据
        """
        self.logger.info(f"更新论文数据: {arxiv_id}")

        try:
            # 单篇论文更新始终使用 API，因为 RSS 不支持按 ID 获取
            if not hasattr(self, 'client'):
                self.client = arxiv.Client(
                    page_size=300,
                    delay_seconds=self.config.misc.request_delay,
                    num_retries=self.config.misc.max_retries,
                )

            search = arxiv.Search(id_list=[arxiv_id])

            for result in self.client.results(search):
                paper = self._convert_arxiv_result_to_paper_data(result)

                # 如果本地存在旧数据，保留翻译信息
                old_paper = self.storage.load_paper(arxiv_id)
                if old_paper and old_paper.is_translated():
                    paper.title_zh = old_paper.title_zh
                    paper.abstract_zh = old_paper.abstract_zh
                    paper.translated_at = old_paper.translated_at

                # 保存更新后的数据
                self.storage.save_paper(paper)

                return paper

            return None

        except Exception as e:
            self.logger.error(f"更新论文数据 {arxiv_id} 时出错: {e}")
            return None

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

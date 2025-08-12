"""
arXiv 论文获取模块
负责从 arXiv 获取指定领域的最新论文
"""

import logging
import time
import re
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

        # arXiv 客户端配置
        self.client = arxiv.Client(
            page_size=100,
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

        try:
            # 使用UTC时间计算日期范围
            now_utc = datetime.now(timezone.utc)
            print(now_utc)
            current_weekday = now_utc.weekday()  # 0=Monday, 6=Sunday
            
            # 根据星期几确定搜索范围
            if current_weekday == 0:  # 星期一
                cutoff_days = 4  # 搜索到上周五
                range_desc = "上周五至今"
            elif current_weekday == 1:  # 星期二 
                cutoff_days = 3  # 搜索到前天
                range_desc = "前3天至今"
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

            # 设置较大的搜索结果数，让我们能搜索到足够多的论文
            search = arxiv.Search(
                query=query,
                max_results=2000,  # 设置一个较大的数量确保能搜到前天的论文
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
                    print(published_date)
                    print(cutoff_date)
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

        # 构建关键词查询
        keyword_query = " OR ".join([f'all:"{keyword}"' for keyword in keywords])

        # 如果指定了类别，添加类别限制
        if category:
            query = f"({keyword_query}) AND cat:{category}"
        else:
            query = keyword_query

        self.logger.info(f"使用关键词搜索论文: {keywords}, 类别: {category}")

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

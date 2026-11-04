"""
处理一个公告日的完整流程：抓列表页 -> 存论文 -> 翻译。
每一步做完都把状态写进当天的 daily 文件，重跑时跳过已经做完的步骤，所以中途挂掉、服务重启都可以接着做。
"""

import logging
import re
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .arxiv_fetcher import ArxivFetcher, FetchResult
from .config import Config
from .listing import ListingEntry
from .storage import DailyListing, PaperData, PaperStorage
from .translator import GPTTranslator

_NORM_RE = re.compile(r"https?://\S+|this https? url|[^a-z0-9]+")


def _norm(text: str) -> str:
    # é -> e：abs 页上是 TeX 的 \'e，列表页上是渲染好的 é
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _NORM_RE.sub("", text.lower())


def _same_text(a: str, b: str) -> bool:
    """只比字母和数字：空白、标点、重音、网址写法不同不算改了（abs 页和列表页来的文字格式略有不同）"""
    return _norm(a) == _norm(b)


class Pipeline:
    def __init__(
        self,
        config: Config,
        storage: PaperStorage,
        fetcher: ArxivFetcher,
        translator: Optional[GPTTranslator],
        use_llm: bool = True,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.config = config
        self.storage = storage
        self.fetcher = fetcher
        self.translator = translator
        self.use_llm = use_llm
        self.clock = clock
        self.logger = logging.getLogger(__name__)

    def _now(self) -> str:
        return self.clock().isoformat(timespec="seconds")

    # ---- 列表页 -> 论文数据 ----

    def _paper_from_entry(self, entry: ListingEntry, date: str) -> PaperData:
        paper = self.storage.load_paper(entry.arxiv_id)
        if paper is None:
            paper = PaperData(
                arxiv_id=entry.arxiv_id,
                title=entry.title,
                authors=entry.authors,
                abstract=entry.abstract,
                published=date,
                categories=entry.categories,
                arxiv_url=f"https://arxiv.org/abs/{entry.arxiv_id}",
                pdf_url=f"https://arxiv.org/pdf/{entry.arxiv_id}",
                hjfy_url=self.config.misc.hjfy_url_template.format(
                    arxiv_id=entry.arxiv_id
                ),
                comments=entry.comments,
                journal_ref=entry.journal_ref,
                primary_category=entry.primary_category or None,
                announced=date,
            )
        else:
            text_changed = (
                entry.title and not _same_text(entry.title, paper.title)
            ) or (entry.abstract and not _same_text(entry.abstract, paper.abstract))
            if text_changed and paper.is_translated():
                self.logger.info(f"{entry.arxiv_id} 的标题或摘要变了，重新翻译")
                paper.title_zh = paper.abstract_zh = paper.translated_at = None
            paper.title = entry.title or paper.title
            paper.abstract = entry.abstract or paper.abstract
            paper.authors = entry.authors or paper.authors
            paper.categories = entry.categories or paper.categories
            paper.comments = entry.comments or paper.comments
            paper.journal_ref = entry.journal_ref or paper.journal_ref
            paper.primary_category = entry.primary_category or paper.primary_category
            paper.announced = paper.announced or date
        self.storage.save_paper(paper)
        return paper

    def build_listing(
        self, fetched: FetchResult, status: Dict[str, Any]
    ) -> DailyListing:
        date = fetched.listing_date.isoformat()
        listing = DailyListing(date=date, status=dict(status))
        # 一篇论文可能出现在几个分类里（cs.CV 的新提交同时是 cs.RO 的 cross-list）：各分类共用同一个对象，
        # 翻译只翻一次，写进当天文件时几个分类里都有中文
        shared: Dict[str, PaperData] = {}
        for category, page in fetched.pages.items():
            papers: List[PaperData] = []
            kinds: Dict[str, str] = {}
            for entry in page.entries:
                if entry.arxiv_id in kinds:
                    continue
                if entry.arxiv_id not in shared:
                    shared[entry.arxiv_id] = self._paper_from_entry(entry, date)
                papers.append(shared[entry.arxiv_id])
                kinds[entry.arxiv_id] = entry.kind
            listing.papers_by_category[category] = papers
            listing.kinds[category] = kinds
            listing.header_counts[category] = dict(page.header_counts)
        return listing

    # ---- 主流程 ----

    def run(
        self, force: bool = False, fetched: Optional[FetchResult] = None
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "listing_date": None,
            "done": False,
            "skipped": None,
            "papers": 0,
            "translated": 0,
            "translate_failed": 0,
            "errors": [],
        }
        fetched = fetched or self.fetcher.fetch_all()
        date = fetched.listing_date.isoformat()
        result["listing_date"] = date

        existing = self.storage.load_daily(date)
        if existing and existing.done and not force:
            result["skipped"] = "already done"
            result["done"] = True
            return result

        if existing is None:
            status: Dict[str, Any] = {}
        elif existing.legacy:
            # 旧代码生成的文件当天已经处理完了；补抓（--force）以后也保持已完成
            status = {"done_at": "legacy"}
        else:
            status = dict(existing.status)
        listing = self.build_listing(fetched, status)
        listing.status["fetched_at"] = self._now()
        self.storage.save_daily(listing)
        papers = listing.unique_papers()
        result["papers"] = len(papers)
        self.logger.info(f"{date}: 共 {len(papers)} 篇（各分类 {listing.counts()}）")

        if self.use_llm and self.translator is not None:
            todo = [p for p in papers if not p.is_translated()]
            translated, failed = self.translator.translate_papers(todo)
            for paper in todo:
                if paper.is_translated():
                    self.storage.save_paper(paper)
            result["translated"], result["translate_failed"] = translated, failed
            listing.status["translated_at"] = self._now()
            listing.status["translate_failed"] = failed
            self.storage.save_daily(listing)

        # 试跑（不调模型）不把这一天标成已完成
        if self.use_llm:
            listing.status["done_at"] = self._now()
            result["done"] = True
            state = self.storage.load_state()
            if (state.get("last_done") or "") < date:
                state["last_done"] = date
                self.storage.save_state(state)
        self.storage.save_daily(listing)

        if self.use_llm:
            self.storage.cleanup_old_data()
        return result

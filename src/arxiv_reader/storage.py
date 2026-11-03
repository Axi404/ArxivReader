"""
数据存储模块
每篇论文一个 JSON（papers/<id>.json，翻译结果也在里面），每个公告日一个汇总（daily/<日期>.json）。
所有写入都先写临时文件再改名，web 服务同时读也不会读到写了一半的文件。
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config

DAILY_FORMAT = 2


@dataclass
class PaperData:
    """论文数据结构"""

    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    published: str  # 旧数据是提交日期；列表页来的是公告日期
    categories: List[str]
    arxiv_url: str
    pdf_url: str

    # 翻译后的内容
    title_zh: Optional[str] = None
    abstract_zh: Optional[str] = None

    # 其他链接
    hjfy_url: Optional[str] = None

    # 元数据
    fetched_at: Optional[str] = None
    translated_at: Optional[str] = None

    # 列表页上的信息（2026-11 起）
    comments: Optional[str] = None
    journal_ref: Optional[str] = None
    primary_category: Optional[str] = None
    announced: Optional[str] = None  # 第一次出现在列表里的公告日期

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperData":
        """从字典创建对象；多出来的字段（比如 daily 文件里的 kind）直接忽略"""
        allowed = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in allowed}
        values.setdefault("published", "")
        values.setdefault("categories", [])
        values.setdefault("authors", [])
        values.setdefault("abstract", "")
        values.setdefault("title", "")
        arxiv_id = values.get("arxiv_id", "")
        values.setdefault("arxiv_url", f"https://arxiv.org/abs/{arxiv_id}")
        values.setdefault("pdf_url", f"https://arxiv.org/pdf/{arxiv_id}")
        return cls(**values)

    def is_translated(self) -> bool:
        return bool(self.title_zh) and bool(self.abstract_zh)

    def set_translation(self, title_zh: str, abstract_zh: str) -> None:
        self.title_zh = title_zh
        self.abstract_zh = abstract_zh
        self.translated_at = datetime.now().isoformat()


@dataclass
class DailyListing:
    """一个公告日的汇总：每个分类下的论文和它在这个分类里的类型（new / cross）"""

    date: str
    papers_by_category: Dict[str, List[PaperData]] = field(default_factory=dict)
    kinds: Dict[str, Dict[str, str]] = field(
        default_factory=dict
    )  # 分类 -> {arxiv_id: kind}
    header_counts: Dict[str, Dict[str, Optional[int]]] = field(default_factory=dict)
    status: Dict[str, Any] = field(default_factory=dict)
    legacy: bool = False  # 2026-11 之前的旧格式文件

    def kind_of(self, category: str, arxiv_id: str) -> str:
        return self.kinds.get(category, {}).get(arxiv_id, "new")

    def unique_papers(self) -> List[PaperData]:
        seen: Dict[str, PaperData] = {}
        for papers in self.papers_by_category.values():
            for paper in papers:
                seen.setdefault(paper.arxiv_id, paper)
        return list(seen.values())

    def counts(self) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        for category, papers in self.papers_by_category.items():
            result[category] = {"new": 0, "cross": 0}
            for paper in papers:
                result[category][self.kind_of(category, paper.arxiv_id)] += 1
        return result

    @property
    def done(self) -> bool:
        """整个流程走完了（旧格式的文件都当作已完成）"""
        return self.legacy or bool(self.status.get("done_at"))

    def to_dict(self) -> Dict[str, Any]:
        serialized = {}
        for category, papers in self.papers_by_category.items():
            serialized[category] = [
                dict(p.to_dict(), kind=self.kind_of(category, p.arxiv_id))
                for p in papers
            ]
        return {
            "date": self.date,
            "format": DAILY_FORMAT,
            "total_papers": len(self.unique_papers()),
            "categories": list(self.papers_by_category.keys()),
            "counts": self.counts(),
            "header_counts": self.header_counts,
            "status": self.status,
            "papers_by_category": serialized,
            "generated_at": datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyListing":
        listing = cls(
            date=data.get("date", ""),
            header_counts=data.get("header_counts") or {},
            status=data.get("status") or {},
            legacy="format" not in data,
        )
        for category, papers in (data.get("papers_by_category") or {}).items():
            listing.papers_by_category[category] = [
                PaperData.from_dict(p) for p in papers
            ]
            listing.kinds[category] = {
                p["arxiv_id"]: p.get("kind", "new") for p in papers
            }
        return listing


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class PaperStorage:
    """论文存储管理器"""

    def __init__(self, config: Config, data_dir: Optional[str] = None):
        self.config = config
        self.data_dir = Path(data_dir or config.storage.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

        self.papers_dir = self.data_dir / "papers"
        self.daily_dir = self.data_dir / "daily"
        self.state_file = self.data_dir / "state.json"
        self.papers_dir.mkdir(exist_ok=True)
        self.daily_dir.mkdir(exist_ok=True)

    # ---- 单篇论文 ----

    def save_paper(self, paper: PaperData) -> bool:
        try:
            if not paper.hjfy_url:
                paper.hjfy_url = self.config.misc.hjfy_url_template.format(
                    arxiv_id=paper.arxiv_id
                )
            atomic_write_json(
                self.papers_dir / f"{paper.arxiv_id}.json", paper.to_dict()
            )
            return True
        except Exception as e:
            self.logger.error(f"保存论文数据失败 {paper.arxiv_id}: {e}")
            return False

    def load_paper(self, arxiv_id: str) -> Optional[PaperData]:
        file_path = self.papers_dir / f"{arxiv_id}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                paper = PaperData.from_dict(json.load(f))
            if not paper.hjfy_url:
                paper.hjfy_url = self.config.misc.hjfy_url_template.format(
                    arxiv_id=paper.arxiv_id
                )
            return paper
        except Exception as e:
            self.logger.error(f"加载论文数据失败 {arxiv_id}: {e}")
            return None

    def count_papers(self) -> int:
        with os.scandir(self.papers_dir) as it:
            return sum(1 for e in it if e.name.endswith(".json"))

    def paper_exists(self, arxiv_id: str) -> bool:
        return (self.papers_dir / f"{arxiv_id}.json").exists()

    # ---- 每日汇总 ----

    def daily_path(self, date: str) -> Path:
        return self.daily_dir / f"{date}.json"

    def list_dates(self) -> List[str]:
        """所有有数据的公告日期，新的在前"""
        dates = []
        for path in self.daily_dir.glob("*.json"):
            try:
                datetime.strptime(path.stem, "%Y-%m-%d")
            except ValueError:
                continue
            dates.append(path.stem)
        return sorted(dates, reverse=True)

    def save_daily(self, listing: DailyListing) -> bool:
        try:
            atomic_write_json(self.daily_path(listing.date), listing.to_dict())
            return True
        except Exception as e:
            self.logger.error(f"保存每日汇总失败 {listing.date}: {e}")
            return False

    def load_daily(self, date: str) -> Optional[DailyListing]:
        data = self.load_daily_papers(date)
        return DailyListing.from_dict(data) if data else None

    def load_daily_papers(self, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """读原始的每日 JSON（web API 直接返回它）"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        file_path = self.daily_path(date)
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"加载每日汇总失败 {date}: {e}")
            return None

    # ---- 调度状态 ----

    def load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"读取调度状态失败: {e}")
            return {}

    def save_state(self, state: Dict[str, Any]) -> None:
        atomic_write_json(self.state_file, state)

    def last_done_date(self) -> Optional[str]:
        """最近一个走完全流程的公告日期"""
        state_date = self.load_state().get("last_done")
        for date in self.list_dates():
            if state_date and date <= state_date:
                return state_date
            listing = self.load_daily(date)
            if listing and listing.done:
                return date
        return state_date

    # ---- 清理和统计 ----

    def cleanup_old_data(self, retention_days: Optional[int] = None) -> None:
        retention_days = retention_days or self.config.storage.retention_days
        if retention_days <= 0:
            self.logger.info("数据保留策略设置为永久保留，跳过清理")
            return

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        self.logger.info(f"开始清理 {cutoff_date.strftime('%Y-%m-%d')} 之前的数据")

        cleaned_daily = 0
        for file_path in self.daily_dir.glob("*.json"):
            try:
                if datetime.strptime(file_path.stem, "%Y-%m-%d") < cutoff_date:
                    file_path.unlink()
                    cleaned_daily += 1
            except (ValueError, OSError) as e:
                self.logger.warning(f"清理文件失败 {file_path}: {e}")

        cleaned_papers = 0
        for file_path in self.papers_dir.glob("*.json"):
            try:
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_date:
                    file_path.unlink()
                    cleaned_papers += 1
            except OSError as e:
                self.logger.warning(f"清理文件失败 {file_path}: {e}")

        self.logger.info(
            f"清理完成: 删除 {cleaned_daily} 个每日汇总文件, {cleaned_papers} 个论文文件"
        )

    def get_statistics(self) -> Dict[str, Any]:
        paper_files = list(self.papers_dir.glob("*.json"))
        daily_files = list(self.daily_dir.glob("*.json"))

        total_size = 0
        for file_path in paper_files + daily_files:
            try:
                total_size += file_path.stat().st_size
            except OSError:
                pass

        dates = self.list_dates()
        return {
            "total_papers": len(paper_files),
            "total_daily_summaries": len(dates),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "date_range": {
                "earliest": dates[-1] if dates else None,
                "latest": dates[0] if dates else None,
            },
        }

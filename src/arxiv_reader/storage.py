"""
数据存储模块
负责论文数据的保存、加载和管理
"""

import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from .config import get_config


@dataclass
class PaperData:
    """论文数据结构"""
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    published: str
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

    def __post_init__(self):
        """初始化后处理"""
        if self.fetched_at is None:
            self.fetched_at = datetime.now().isoformat()
        
        if self.hjfy_url is None:
            config = get_config()
            self.hjfy_url = config.misc.hjfy_url_template.format(arxiv_id=self.arxiv_id)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PaperData':
        """从字典创建对象"""
        return cls(**data)

    def is_translated(self) -> bool:
        """检查是否已翻译"""
        return self.title_zh is not None and self.abstract_zh is not None

    def set_translation(self, title_zh: str, abstract_zh: str) -> None:
        """设置翻译结果"""
        self.title_zh = title_zh
        self.abstract_zh = abstract_zh
        self.translated_at = datetime.now().isoformat()


class PaperStorage:
    """论文存储管理器"""
    
    def __init__(self, data_dir: Optional[str] = None):
        """
        初始化存储管理器
        
        Args:
            data_dir: 数据目录路径，如果为None则使用配置中的路径
        """
        config = get_config()
        self.data_dir = Path(data_dir or config.storage.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        
        # 创建子目录
        self.papers_dir = self.data_dir / "papers"
        self.daily_dir = self.data_dir / "daily"
        self.papers_dir.mkdir(exist_ok=True)
        self.daily_dir.mkdir(exist_ok=True)

    def save_paper(self, paper: PaperData) -> bool:
        """
        保存单篇论文数据
        
        Args:
            paper: 论文数据对象
            
        Returns:
            是否保存成功
        """
        try:
            file_path = self.papers_dir / f"{paper.arxiv_id}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(paper.to_dict(), f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"保存论文数据: {paper.arxiv_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存论文数据失败 {paper.arxiv_id}: {e}")
            return False

    def load_paper(self, arxiv_id: str) -> Optional[PaperData]:
        """
        加载单篇论文数据
        
        Args:
            arxiv_id: arXiv ID
            
        Returns:
            论文数据对象，如果不存在则返回None
        """
        try:
            file_path = self.papers_dir / f"{arxiv_id}.json"
            
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return PaperData.from_dict(data)
            
        except Exception as e:
            self.logger.error(f"加载论文数据失败 {arxiv_id}: {e}")
            return None

    def paper_exists(self, arxiv_id: str) -> bool:
        """
        检查论文是否已存在
        
        Args:
            arxiv_id: arXiv ID
            
        Returns:
            是否存在
        """
        file_path = self.papers_dir / f"{arxiv_id}.json"
        return file_path.exists()

    def save_daily_papers(self, papers: List[PaperData], date: Optional[str] = None) -> bool:
        """
        保存每日论文汇总
        
        Args:
            papers: 论文列表
            date: 日期字符串，如果为None则使用今天
            
        Returns:
            是否保存成功
        """
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            file_path = self.daily_dir / f"{date}.json"
            
            # 按类别分组
            papers_by_category = {}
            for paper in papers:
                for category in paper.categories:
                    if category not in papers_by_category:
                        papers_by_category[category] = []
                    papers_by_category[category].append(paper.to_dict())
            
            daily_data = {
                "date": date,
                "total_papers": len(papers),
                "categories": list(papers_by_category.keys()),
                "papers_by_category": papers_by_category,
                "generated_at": datetime.now().isoformat()
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(daily_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"保存每日论文汇总: {date}, 共 {len(papers)} 篇")
            return True
            
        except Exception as e:
            self.logger.error(f"保存每日论文汇总失败: {e}")
            return False

    def load_daily_papers(self, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        加载每日论文汇总
        
        Args:
            date: 日期字符串，如果为None则使用今天
            
        Returns:
            每日论文数据，如果不存在则返回None
        """
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            file_path = self.daily_dir / f"{date}.json"
            
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
            
        except Exception as e:
            self.logger.error(f"加载每日论文汇总失败: {e}")
            return None

    def get_papers_by_category(self, category: str, days: int = 7) -> List[PaperData]:
        """
        获取指定类别最近几天的论文
        
        Args:
            category: 类别名称
            days: 天数
            
        Returns:
            论文列表
        """
        papers = []
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_data = self.load_daily_papers(date)
            
            if daily_data and category in daily_data.get("papers_by_category", {}):
                category_papers = daily_data["papers_by_category"][category]
                papers.extend([PaperData.from_dict(p) for p in category_papers])
        
        return papers

    def cleanup_old_data(self, retention_days: Optional[int] = None) -> None:
        """
        清理过期数据
        
        Args:
            retention_days: 保留天数，如果为None则使用配置中的值
        """
        config = get_config()
        retention_days = retention_days or config.storage.retention_days
        
        if retention_days <= 0:
            self.logger.info("数据保留策略设置为永久保留，跳过清理")
            return
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        self.logger.info(f"开始清理 {cutoff_date.strftime('%Y-%m-%d')} 之前的数据")
        
        # 清理每日汇总文件
        cleaned_daily = 0
        for file_path in self.daily_dir.glob("*.json"):
            try:
                file_date = datetime.strptime(file_path.stem, "%Y-%m-%d")
                if file_date < cutoff_date:
                    file_path.unlink()
                    cleaned_daily += 1
            except (ValueError, OSError) as e:
                self.logger.warning(f"清理文件失败 {file_path}: {e}")
        
        # 清理论文文件（基于文件修改时间）
        cleaned_papers = 0
        for file_path in self.papers_dir.glob("*.json"):
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_date:
                    file_path.unlink()
                    cleaned_papers += 1
            except OSError as e:
                self.logger.warning(f"清理文件失败 {file_path}: {e}")
        
        self.logger.info(f"清理完成: 删除 {cleaned_daily} 个每日汇总文件, {cleaned_papers} 个论文文件")

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            统计信息字典
        """
        paper_files = list(self.papers_dir.glob("*.json"))
        daily_files = list(self.daily_dir.glob("*.json"))
        
        # 计算存储大小
        total_size = 0
        for file_path in paper_files + daily_files:
            try:
                total_size += file_path.stat().st_size
            except OSError:
                pass
        
        # 计算日期范围
        dates = []
        for file_path in daily_files:
            try:
                date = datetime.strptime(file_path.stem, "%Y-%m-%d")
                dates.append(date)
            except ValueError:
                pass
        
        stats = {
            "total_papers": len(paper_files),
            "total_daily_summaries": len(daily_files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "date_range": {
                "earliest": min(dates).strftime("%Y-%m-%d") if dates else None,
                "latest": max(dates).strftime("%Y-%m-%d") if dates else None
            }
        }
        
        return stats


# 全局存储对象
_storage: PaperStorage = None


def get_storage() -> PaperStorage:
    """获取全局存储对象"""
    global _storage
    if _storage is None:
        _storage = PaperStorage()
    return _storage
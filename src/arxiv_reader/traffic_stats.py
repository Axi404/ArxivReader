"""
流量统计模块
统计每小时、每日和总访问量，每小时自动保存到文件
"""

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TrafficStats:
    """流量统计管理器"""

    def __init__(self, data_dir: Optional[Path] = None):
        """
        初始化流量统计

        Args:
            data_dir: 数据存储目录，默认为项目根目录下的 data/traffic/
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data" / "traffic"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.stats_file = self.data_dir / "traffic_stats.json"

        # 内存中的计数器
        self._lock = threading.Lock()
        self._hourly_counts: Dict[str, int] = defaultdict(
            int
        )  # "YYYY-MM-DD-HH" -> count
        self._daily_counts: Dict[str, int] = defaultdict(int)  # "YYYY-MM-DD" -> count
        self._total_count: int = 0

        # 上次保存的小时
        self._last_saved_hour: Optional[str] = None

        # 加载已有数据
        self._load_stats()

        # 启动后台保存线程
        self._stop_event = threading.Event()
        self._save_thread = threading.Thread(target=self._periodic_save, daemon=True)
        self._save_thread.start()

        logger.info(f"流量统计已初始化，数据目录: {self.data_dir}")

    def _load_stats(self) -> None:
        """从文件加载统计数据"""
        if not self.stats_file.exists():
            return

        try:
            with open(self.stats_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._hourly_counts = defaultdict(int, data.get("hourly", {}))
            self._daily_counts = defaultdict(int, data.get("daily", {}))
            self._total_count = data.get("total", 0)
            self._last_saved_hour = data.get("last_saved_hour")

            logger.info(f"已加载流量统计: 总访问 {self._total_count}")
        except Exception as e:
            logger.error(f"加载流量统计失败: {e}")

    def _save_stats(self) -> None:
        """保存统计数据到文件"""
        with self._lock:
            data = {
                "hourly": dict(self._hourly_counts),
                "daily": dict(self._daily_counts),
                "total": self._total_count,
                "last_saved_hour": self._get_current_hour(),
                "last_updated": datetime.now().isoformat(),
            }

        try:
            # 先写临时文件再重命名，保证原子性
            tmp_file = self.stats_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_file.replace(self.stats_file)
            logger.debug("流量统计已保存")
        except Exception as e:
            logger.error(f"保存流量统计失败: {e}")

    def _periodic_save(self) -> None:
        """后台定期保存线程"""
        while not self._stop_event.is_set():
            current_hour = self._get_current_hour()

            # 每小时保存一次
            if self._last_saved_hour != current_hour:
                self._save_stats()
                self._last_saved_hour = current_hour
                logger.info(f"流量统计已自动保存 (小时: {current_hour})")

            # 每分钟检查一次
            self._stop_event.wait(60)

    @staticmethod
    def _get_current_hour() -> str:
        """获取当前小时标识"""
        return datetime.now().strftime("%Y-%m-%d-%H")

    @staticmethod
    def _get_current_date() -> str:
        """获取当前日期标识"""
        return datetime.now().strftime("%Y-%m-%d")

    def record_visit(self) -> None:
        """记录一次访问"""
        current_hour = self._get_current_hour()
        current_date = self._get_current_date()

        with self._lock:
            self._hourly_counts[current_hour] += 1
            self._daily_counts[current_date] += 1
            self._total_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        current_hour = self._get_current_hour()
        current_date = self._get_current_date()

        with self._lock:
            # 获取最近24小时的数据
            recent_hours = []
            now = datetime.now()
            for i in range(24):
                hour_dt = now.replace(minute=0, second=0, microsecond=0)
                from datetime import timedelta

                hour_dt = hour_dt - timedelta(hours=i)
                hour_key = hour_dt.strftime("%Y-%m-%d-%H")
                recent_hours.append(
                    {
                        "hour": hour_dt.strftime("%H:00"),
                        "date": hour_dt.strftime("%Y-%m-%d"),
                        "count": self._hourly_counts.get(hour_key, 0),
                    }
                )

            # 获取最近7天的数据
            recent_days = []
            for i in range(7):
                day_dt = now - timedelta(days=i)
                day_key = day_dt.strftime("%Y-%m-%d")
                recent_days.append(
                    {
                        "date": day_key,
                        "count": self._daily_counts.get(day_key, 0),
                    }
                )

            return {
                "current_hour": self._hourly_counts.get(current_hour, 0),
                "current_day": self._daily_counts.get(current_date, 0),
                "total": self._total_count,
                "recent_hours": list(reversed(recent_hours)),
                "recent_days": list(reversed(recent_days)),
                "last_updated": datetime.now().isoformat(),
            }

    def get_summary(self) -> Dict[str, int]:
        """获取简要统计（用于首页显示）"""
        current_hour = self._get_current_hour()
        current_date = self._get_current_date()

        with self._lock:
            return {
                "hourly": self._hourly_counts.get(current_hour, 0),
                "daily": self._daily_counts.get(current_date, 0),
                "total": self._total_count,
            }

    def shutdown(self) -> None:
        """关闭统计器，保存数据"""
        self._stop_event.set()
        self._save_thread.join(timeout=5)
        self._save_stats()
        logger.info("流量统计已关闭并保存")


# 全局单例
_traffic_stats: Optional[TrafficStats] = None


def get_traffic_stats(data_dir: Optional[Path] = None) -> TrafficStats:
    """获取流量统计单例"""
    global _traffic_stats
    if _traffic_stats is None:
        _traffic_stats = TrafficStats(data_dir)
    return _traffic_stats


def shutdown_traffic_stats() -> None:
    """关闭流量统计"""
    global _traffic_stats
    if _traffic_stats is not None:
        _traffic_stats.shutdown()
        _traffic_stats = None

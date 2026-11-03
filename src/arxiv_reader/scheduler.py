"""
定时任务模块
守护进程不再按固定时刻跑，而是在 arXiv 预计公告之后每隔几分钟看一次列表页：出了新的公告日就处理，
处理完就安静地等下一次公告。状态都在磁盘上（daily 文件和 data/state.json），重启不会丢。
"""

import argparse
import logging
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .arxiv_fetcher import ListingNotReady

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
ANNOUNCE_TIME_ET = dtime(
    20, 0
)  # arXiv 周日到周四美东 20:00 公告，列表页上的日期是第二天
EARLY_MINUTES = 5


def next_listing_date(d: date) -> date:
    """d 之后的下一个公告日（周一到周五）"""
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return n


def expected_announcement(listing_date: date) -> datetime:
    """某个公告日的列表预计什么时候出来（UTC）：前一天美东 20:00；周一的在周日晚上"""
    previous_day = listing_date - timedelta(days=1)
    return datetime.combine(previous_day, ANNOUNCE_TIME_ET, tzinfo=ET).astimezone(UTC)


class ArxivScheduler:
    """轮询调度器"""

    def __init__(
        self,
        reader,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.reader = reader
        self.config = reader.config
        self.storage = reader.storage
        self.logger = logging.getLogger(__name__)
        self.clock = clock
        self.sleep = sleep
        self.local_tz = ZoneInfo(self.config.schedule.timezone)
        self.interval = timedelta(minutes=self.config.schedule.poll_interval_minutes)
        self.last_check: Optional[datetime] = None
        self.last_done: Optional[str] = self.storage.last_done_date()
        self.is_running = False
        self._waiting_logged_for: Optional[datetime] = None

    # ---- 时间 ----

    def poll_start(self) -> Optional[datetime]:
        """从什么时候开始轮询；None 表示马上（还没有处理过任何一天）"""
        if not self.last_done:
            return None
        nxt = next_listing_date(date.fromisoformat(self.last_done))
        return expected_announcement(nxt) - timedelta(minutes=EARLY_MINUTES)

    # ---- 每一拍 ----

    def tick(self, now: Optional[datetime] = None) -> str:
        now = now or self.clock()
        start = self.poll_start()
        if start is not None and now < start:
            if self._waiting_logged_for != start:
                self._waiting_logged_for = start
                self.logger.info(
                    f"{self.last_done} 已处理完，下一次公告预计在 "
                    f"{(start + timedelta(minutes=EARLY_MINUTES)).astimezone(self.local_tz):%m-%d %H:%M}"
                    f"（{self.config.schedule.timezone}），到时开始轮询"
                )
            return "waiting"
        if self.last_check is not None and now - self.last_check < self.interval:
            return "interval"
        self.last_check = now

        try:
            listing_date = self.reader.fetcher.peek_listing_date()
        except Exception as exc:
            self.logger.warning(f"查看列表页失败: {exc}")
            return "error"
        if listing_date is None:
            self.logger.warning("列表页上没找到日期")
            return "error"

        if self.last_done and listing_date.isoformat() <= self.last_done:
            self.logger.info(
                f"列表页还是 {listing_date}，{self.interval.seconds // 60} 分钟后再看"
            )
            return "not-yet"

        try:
            result = self.reader.run_once()
        except ListingNotReady as exc:
            self.logger.info(f"列表页还没全部更新: {exc}")
            return "not-ready"
        except Exception as exc:
            self.logger.exception(f"处理 {listing_date} 失败: {exc}")
            return "error"
        if result.get("done"):
            self.last_done = result["listing_date"]
            return "done"
        return "partial"

    # ---- 循环 ----

    def run_forever(self, tick_seconds: float = 30.0) -> None:
        self.is_running = True
        self.logger.info(
            f"调度器启动：轮询间隔 {self.interval.seconds // 60} 分钟，最近处理完的公告日 {self.last_done}"
        )
        while self.is_running:
            try:
                self.tick()
            except Exception as exc:  # 不让一次异常把守护进程带走
                self.logger.exception(f"调度出错: {exc}")
            self.sleep(tick_seconds)

    def stop(self) -> None:
        self.is_running = False


def run_daemon(config_path: str = "config/config.yaml") -> None:
    from .main import ArxivReader

    reader = ArxivReader(config_path)
    if not reader.config.schedule.enabled:
        print("❌ 定时任务已禁用，无法启动守护进程")
        return
    scheduler = ArxivScheduler(reader)
    print("🚀 arXiv Reader 守护进程已启动（轮询模式）")
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        print("\n🛑 收到停止信号，已停止")


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv Reader 调度器")
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    args = parser.parse_args()
    run_daemon(args.config)


if __name__ == "__main__":
    main()

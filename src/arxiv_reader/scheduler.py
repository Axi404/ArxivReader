"""
定时任务模块
守护进程不再按固定时刻跑，而是在 arXiv 预计公告之后每隔几分钟看一次列表页：出了新的公告日就处理，
处理完就安静地等下一次公告。状态都在磁盘上（daily 文件和 data/state.json），重启不会丢。

兜底：arXiv 的列表页偶尔会在上一天停好几个小时（这时 abs 页和 OAI-PMH 已经有当天的论文）。
预计公告时间过了 fallback_after_minutes 还没等到，就从 OAI-PMH 拼出当天的列表先处理；
列表页之后恢复到这一天时，再用列表页把它过一遍（补上 OAI 拼不出的老论文 cross-list）。
列表页要是直接跳过了某个公告日，处理新的一天之前先用 OAI 把跳过的那天补上。
"""

import argparse
import logging
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Callable, Dict, Optional, Tuple
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
        self.last_fallback: Optional[datetime] = None
        # OAI 兜底上次看到的每个公告日的条数：连续两次一样才处理，免得 OAI 还没索引完就当成一整天
        self._oai_seen: Dict[str, int] = {}
        self._source_cache: Dict[str, Tuple[float, Optional[str]]] = {}

    # ---- 时间 ----

    def poll_start(self) -> Optional[datetime]:
        """从什么时候开始轮询；None 表示马上（还没有处理过任何一天）"""
        if not self.last_done:
            return None
        nxt = next_listing_date(date.fromisoformat(self.last_done))
        return expected_announcement(nxt) - timedelta(minutes=EARLY_MINUTES)

    # ---- 每一拍 ----

    def _from_oai(self, day: Optional[str]) -> bool:
        """这一天是不是 OAI 兜底拼的（还没用列表页过一遍）；按文件修改时间缓存，免得每次 tick 都读一遍"""
        if not day:
            return False
        path = self.storage.daily_path(day)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False
        cached = self._source_cache.get(day)
        if cached is None or cached[0] != mtime:
            daily = self.storage.load_daily(day)
            source = daily.status.get("source") if daily else None
            cached = (mtime, source)
            self._source_cache[day] = cached
        return cached[1] == "oai"

    def _last_done_from_oai(self) -> bool:
        return self._from_oai(self.last_done)

    def _fallback_due(self, now: datetime) -> bool:
        minutes = self.config.schedule.fallback_after_minutes
        if not minutes or minutes <= 0 or not self.last_done:
            return False
        nxt = next_listing_date(date.fromisoformat(self.last_done))
        if now < expected_announcement(nxt) + timedelta(minutes=minutes):
            return False
        interval = timedelta(minutes=self.config.schedule.fallback_interval_minutes)
        return self.last_fallback is None or now - self.last_fallback >= interval

    def _process_oai(
        self,
        start: date,
        end: Optional[date],
        before: Optional[date] = None,
        require_stable: bool = False,
    ) -> int:
        """从 OAI 拼出 [start, end] 的公告日并依次处理（只处理 last_done 之后、before 之前的）；返回处理完的天数

        require_stable：最新的一天的条数要和上一次兜底时看到的一样才处理（当天的公告 OAI 可能还在索引）
        """
        after_id = self.storage.max_arxiv_id(self.last_done) if self.last_done else None
        try:
            results = self.reader.fetcher.fetch_oai(start, end, after_id=after_id)
        except Exception as exc:
            self.logger.warning(f"OAI-PMH 兜底失败: {exc}")
            return 0
        processed = 0
        latest = max((r.listing_date for r in results), default=None)
        for fetched in results:
            day = fetched.listing_date.isoformat()
            if self.last_done and day <= self.last_done:
                continue
            if before is not None and fetched.listing_date >= before:
                continue
            # OAI 上已经有后面的公告日了，这一天肯定索引完了；只有最新的一天要等数量稳定
            if require_stable and fetched.listing_date == latest:
                count = sum(len(page.entries) for page in fetched.pages.values())
                previous = self._oai_seen.get(day)
                self._oai_seen[day] = count
                if previous != count:
                    self.logger.info(
                        f"OAI-PMH 上 {day} 有 {count} 条（上次 {previous}），等下一次兜底确认数量不再变"
                    )
                    break  # 后面的日子要等这一天先处理
            try:
                result = self.reader.run_fetched(fetched)
            except Exception as exc:
                self.logger.exception(f"用 OAI 处理 {day} 失败: {exc}")
                continue
            if result.get("done"):
                self.last_done = result["listing_date"]
                processed += 1
        return processed

    def tick(self, now: Optional[datetime] = None) -> str:
        now = now or self.clock()
        start = self.poll_start()
        # 上一天是 OAI 兜底拼的：一直看列表页，等它恢复到这一天时再用列表页过一遍
        if start is not None and now < start and not self._last_done_from_oai():
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
            # 列表页恢复到了某个 OAI 拼的日子（一般就是 last_done；卡了两天的话也可能是前一天）
            if self._from_oai(listing_date.isoformat()):
                self.logger.info(
                    f"列表页恢复到 {listing_date}，用列表页把这一天再过一遍"
                )
                try:
                    result = self.reader.run_once(force=True)
                except ListingNotReady as exc:
                    self.logger.info(f"列表页还没全部更新: {exc}")
                    return "not-ready"
                except Exception as exc:
                    self.logger.exception(f"用列表页重过 {listing_date} 失败: {exc}")
                    return "error"
                return "reconciled" if result.get("done") else "partial"
            if self._fallback_due(now):
                self.last_fallback = now
                nxt = next_listing_date(date.fromisoformat(self.last_done))
                self.logger.info(
                    f"列表页还停在 {listing_date}，预计公告已经过了 "
                    f"{self.config.schedule.fallback_after_minutes} 分钟，改从 OAI-PMH 拼 {nxt} 起的列表"
                )
                if self._process_oai(nxt, None, require_stable=True):
                    return "fallback"
            self.logger.info(
                f"列表页还是 {listing_date}，{self.interval.seconds // 60} 分钟后再看"
            )
            return "not-yet"

        if self._last_done_from_oai():
            self.logger.warning(
                f"列表页从上一天直接跳到了 {listing_date}，{self.last_done} 只有 OAI 拼的版本，"
                "编号更早、当天新 cross-list 进来的老论文可能缺一两篇"
            )
        # 列表页跳过了中间的公告日（卡了一整天、直接到了下一天）：先用 OAI 把跳过的补上
        if self.last_done and self.config.schedule.fallback_after_minutes:
            nxt = next_listing_date(date.fromisoformat(self.last_done))
            if nxt < listing_date:
                self.logger.info(
                    f"列表页从 {self.last_done} 跳到了 {listing_date}，先从 OAI-PMH 补中间的公告日"
                )
                # 不设 until：跳过那天的论文后来换了版本的话，datestamp 已经是后面的日子了
                self._process_oai(nxt, None, before=listing_date)

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

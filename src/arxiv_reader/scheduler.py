"""
定时任务模块
负责定时执行每日论文获取和推送任务
"""

import argparse
import logging
import time
import threading
from datetime import datetime, time as datetime_time, timedelta
from typing import Optional, Dict, Any

import schedule
import pytz

from .main import ArxivReader


class ArxivScheduler:
    """arXiv 定时调度器"""

    def __init__(self, reader: ArxivReader):
        self.reader = reader
        self.config = reader.config
        self.logger = logging.getLogger(__name__)
        self.timezone = pytz.timezone(self.config.schedule.timezone)

        self.is_running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.last_run_time: Optional[datetime] = None
        self.last_run_result: Optional[Dict[str, Any]] = None
        self.retry_interval_hours = 1  # 重试间隔（小时）

        self._setup_schedule()

    def _calculate_local_time(self) -> str:
        time_parts = self.config.schedule.daily_time.split(":")
        if len(time_parts) != 2:
            raise ValueError(f"无效的时间格式: {self.config.schedule.daily_time}")

        hour, minute = int(time_parts[0]), int(time_parts[1])
        config_tz = pytz.timezone(self.config.schedule.timezone)
        today = datetime.now(config_tz).date()
        config_datetime = config_tz.localize(
            datetime.combine(today, datetime_time(hour, minute))
        )
        local_datetime = config_datetime.astimezone()
        return local_datetime.strftime("%H:%M")

    def _setup_schedule(self) -> None:
        if not self.config.schedule.enabled:
            self.logger.info("定时任务已禁用")
            return

        local_time = self._calculate_local_time()
        schedule.every().day.at(local_time).do(self._run_daily_job)
        self.logger.info("定时任务已设置")
        self.logger.info(f"  配置时区: {self.config.schedule.timezone}")
        self.logger.info(f"  配置时间: {self.config.schedule.daily_time}")
        self.logger.info(f"  服务器本地时间: {local_time}")

    def _clear_retry_jobs(self) -> None:
        """清除所有重试任务"""
        schedule.clear("retry")

    def _schedule_retry(self) -> None:
        """安排一小时后重试"""
        self._clear_retry_jobs()

        # 计算一小时后的时间
        now = datetime.now()
        retry_time = now + timedelta(hours=self.retry_interval_hours)
        retry_time_str = retry_time.strftime("%H:%M")

        schedule.every().day.at(retry_time_str).do(self._run_retry_job).tag("retry")
        self.logger.info(
            f"已安排 {self.retry_interval_hours} 小时后重试 (本地时间 {retry_time_str})"
        )

    def _run_retry_job(self) -> None:
        """执行重试任务"""
        self.logger.info("=" * 60)
        self.logger.info("开始执行重试任务")
        self.logger.info("=" * 60)

        self._clear_retry_jobs()  # 清除当前重试任务，避免重复执行

        self.last_run_time = datetime.now(self.timezone)
        self.last_run_result = self.reader.run_once()

        # 如果仍然不是今天的数据，继续安排重试
        if self.last_run_result.get("not_today"):
            self.logger.warning("arXiv 页面仍未更新到今天，将在 1 小时后重试")
            self._schedule_retry()
        else:
            self.logger.info("重试任务执行成功")

        self.logger.info("=" * 60)
        self.logger.info("重试任务执行完成")
        self.logger.info("=" * 60)

        return schedule.CancelJob  # 取消当前的一次性任务

    def _run_daily_job(self) -> None:
        self.logger.info("=" * 60)
        self.logger.info("开始执行定时任务")
        self.logger.info("=" * 60)

        self._clear_retry_jobs()  # 清除之前可能存在的重试任务

        self.last_run_time = datetime.now(self.timezone)
        self.last_run_result = self.reader.run_once()

        # 如果 arXiv 页面日期不是今天，安排重试
        if self.last_run_result.get("not_today"):
            self.logger.warning("arXiv 页面尚未更新到今天，将在 1 小时后重试")
            self._schedule_retry()

        self.logger.info("=" * 60)
        self.logger.info("定时任务执行完成")
        self.logger.info("=" * 60)

    def _scheduler_worker(self) -> None:
        self.logger.info("调度器线程启动")
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)
        self.logger.info("调度器线程停止")

    def start(self) -> None:
        if self.is_running:
            self.logger.warning("调度器已在运行")
            return

        if not self.config.schedule.enabled:
            self.logger.warning("定时任务已禁用，无法启动调度器")
            return

        self.is_running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_worker, daemon=True
        )
        self.scheduler_thread.start()
        self.logger.info("调度器已启动")

    def stop(self) -> None:
        if not self.is_running:
            self.logger.warning("调度器未在运行")
            return

        self.is_running = False
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        self.logger.info("调度器已停止")

    def get_next_run_time(self) -> Optional[datetime]:
        if not self.config.schedule.enabled:
            return None
        jobs = schedule.get_jobs()
        if not jobs:
            return None
        next_run = min(job.next_run for job in jobs)
        if next_run.tzinfo is None:
            local_datetime = datetime.now().astimezone()
            return next_run.replace(tzinfo=local_datetime.tzinfo)
        return next_run


def run_daemon(config_path: str = "config/config.yaml") -> None:
    reader = ArxivReader(config_path)
    if not reader.config.schedule.enabled:
        print("❌ 定时任务已禁用，无法启动守护进程")
        return
    scheduler = ArxivScheduler(reader)

    try:
        scheduler.start()
        print("🚀 arXiv Reader 守护进程已启动")
        print(f"📅 每日执行时间: {scheduler.config.schedule.daily_time}")
        print(f"🌍 时区: {scheduler.config.schedule.timezone}")

        next_run = scheduler.get_next_run_time()
        if next_run:
            print(f"⏰ 下次运行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        print("按 Ctrl+C 停止守护进程")
        while True:
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n🛑 收到停止信号，正在关闭...")
        scheduler.stop()
        print("✅ 守护进程已停止")

    except Exception as exc:
        print(f"❌ 守护进程异常: {exc}")
        scheduler.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv Reader 调度器")
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    args = parser.parse_args()
    run_daemon(args.config)


if __name__ == "__main__":
    main()

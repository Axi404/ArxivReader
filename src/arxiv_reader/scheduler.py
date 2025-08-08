"""
定时任务模块
负责定时执行每日论文获取和推送任务
"""

import logging
import time
import threading
from datetime import datetime, time as datetime_time
from typing import Optional, Callable, Any
import schedule
import pytz

from .config import get_config
from .main import ArxivReader


class ArxivScheduler:
    """arXiv 定时调度器"""
    
    def __init__(self, reader: Optional[ArxivReader] = None):
        """
        初始化调度器
        
        Args:
            reader: ArxivReader 实例，如果为None则创建新实例
        """
        self.config = get_config()
        self.logger = logging.getLogger(__name__)
        
        # 创建或使用传入的 reader
        self.reader = reader or ArxivReader()
        
        # 调度器状态
        self.is_running = False
        self.scheduler_thread = None
        self.last_run_time = None
        self.last_run_result = None
        
        # 设置时区
        self.timezone = pytz.timezone(self.config.schedule.timezone)
        
        # 配置调度任务
        self._setup_schedule()

    def _setup_schedule(self) -> None:
        """设置调度任务"""
        if not self.config.schedule.enabled:
            self.logger.info("定时任务已禁用")
            return
        
        # 解析时间
        time_parts = self.config.schedule.daily_time.split(":")
        if len(time_parts) != 2:
            self.logger.error(f"无效的时间格式: {self.config.schedule.daily_time}")
            return
        
        try:
            hour = int(time_parts[0])
            minute = int(time_parts[1])
        except ValueError:
            self.logger.error(f"无效的时间格式: {self.config.schedule.daily_time}")
            return
        
        # 添加每日任务
        schedule.every().day.at(self.config.schedule.daily_time).do(self._run_daily_job)
        
        self.logger.info(f"已配置每日任务: {self.config.schedule.daily_time} ({self.config.schedule.timezone})")

    def _run_daily_job(self) -> None:
        """运行每日任务"""
        self.logger.info("=" * 60)
        self.logger.info("开始执行定时任务")
        self.logger.info("=" * 60)
        
        try:
            # 记录开始时间
            self.last_run_time = datetime.now(self.timezone)
            
            # 运行每日工作流程
            result = self.reader.run_daily_workflow()
            self.last_run_result = result
            
            # 记录结果
            if result["success"]:
                self.logger.info("✅ 定时任务执行成功")
                self.logger.info(f"获取论文: {result['papers_fetched']} 篇")
                self.logger.info(f"翻译论文: {result['papers_translated']} 篇")
                self.logger.info(f"邮件发送: {'成功' if result['email_sent'] else '失败'}")
            else:
                self.logger.error("❌ 定时任务执行失败")
                for error in result.get("errors", []):
                    self.logger.error(f"错误: {error}")
        
        except Exception as e:
            self.logger.error(f"定时任务执行异常: {e}")
            self.last_run_result = {
                "success": False,
                "errors": [str(e)],
                "start_time": datetime.now(self.timezone).isoformat()
            }
        
        finally:
            self.logger.info("=" * 60)
            self.logger.info("定时任务执行完成")
            self.logger.info("=" * 60)

    def _scheduler_worker(self) -> None:
        """调度器工作线程"""
        self.logger.info("调度器线程启动")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                self.logger.error(f"调度器线程异常: {e}")
                time.sleep(60)
        
        self.logger.info("调度器线程停止")

    def start(self) -> None:
        """启动调度器"""
        if self.is_running:
            self.logger.warning("调度器已在运行")
            return
        
        if not self.config.schedule.enabled:
            self.logger.warning("定时任务已禁用，无法启动调度器")
            return
        
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_worker, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info("调度器已启动")

    def stop(self) -> None:
        """停止调度器"""
        if not self.is_running:
            self.logger.warning("调度器未在运行")
            return
        
        self.is_running = False
        
        # 等待线程结束
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        self.logger.info("调度器已停止")

    def run_now(self) -> dict:
        """
        立即运行一次任务
        
        Returns:
            任务执行结果
        """
        self.logger.info("手动触发执行任务")
        
        try:
            result = self.reader.run_daily_workflow()
            self.last_run_time = datetime.now(self.timezone)
            self.last_run_result = result
            return result
        
        except Exception as e:
            error_result = {
                "success": False,
                "errors": [str(e)],
                "start_time": datetime.now(self.timezone).isoformat()
            }
            self.last_run_result = error_result
            return error_result

    def get_next_run_time(self) -> Optional[datetime]:
        """
        获取下次运行时间
        
        Returns:
            下次运行时间，如果没有调度任务则返回None
        """
        if not self.config.schedule.enabled:
            return None
        
        jobs = schedule.get_jobs()
        if not jobs:
            return None
        
        # 获取最近的下次运行时间
        next_run = min(job.next_run for job in jobs)
        
        # 转换为本地时区
        return self.timezone.localize(next_run) if next_run.tzinfo is None else next_run

    def get_status(self) -> dict:
        """
        获取调度器状态
        
        Returns:
            调度器状态信息
        """
        next_run = self.get_next_run_time()
        
        status = {
            "enabled": self.config.schedule.enabled,
            "running": self.is_running,
            "daily_time": self.config.schedule.daily_time,
            "timezone": self.config.schedule.timezone,
            "next_run_time": next_run.isoformat() if next_run else None,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_run_success": self.last_run_result.get("success") if self.last_run_result else None,
            "scheduled_jobs_count": len(schedule.get_jobs())
        }
        
        return status

    def update_schedule(self, daily_time: Optional[str] = None, 
                       timezone: Optional[str] = None,
                       enabled: Optional[bool] = None) -> bool:
        """
        更新调度配置
        
        Args:
            daily_time: 新的每日执行时间
            timezone: 新的时区
            enabled: 是否启用
            
        Returns:
            是否更新成功
        """
        try:
            # 停止当前调度器
            was_running = self.is_running
            if was_running:
                self.stop()
            
            # 清除现有任务
            schedule.clear()
            
            # 更新配置
            if daily_time is not None:
                self.config.schedule.daily_time = daily_time
            
            if timezone is not None:
                self.config.schedule.timezone = timezone
                self.timezone = pytz.timezone(timezone)
            
            if enabled is not None:
                self.config.schedule.enabled = enabled
            
            # 重新设置调度
            self._setup_schedule()
            
            # 如果之前在运行，重新启动
            if was_running and self.config.schedule.enabled:
                self.start()
            
            self.logger.info("调度配置已更新")
            return True
        
        except Exception as e:
            self.logger.error(f"更新调度配置失败: {e}")
            return False

    def test_schedule(self) -> dict:
        """
        测试调度配置
        
        Returns:
            测试结果
        """
        result = {
            "config_valid": True,
            "timezone_valid": True,
            "time_format_valid": True,
            "errors": []
        }
        
        # 验证时区
        try:
            pytz.timezone(self.config.schedule.timezone)
        except Exception as e:
            result["timezone_valid"] = False
            result["errors"].append(f"无效的时区: {e}")
        
        # 验证时间格式
        try:
            time_parts = self.config.schedule.daily_time.split(":")
            if len(time_parts) != 2:
                raise ValueError("时间格式应为 HH:MM")
            
            hour, minute = int(time_parts[0]), int(time_parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("时间超出有效范围")
        
        except Exception as e:
            result["time_format_valid"] = False
            result["errors"].append(f"无效的时间格式: {e}")
        
        result["config_valid"] = result["timezone_valid"] and result["time_format_valid"]
        
        return result


def create_daemon_scheduler(config_path: str = "config/config.yaml") -> ArxivScheduler:
    """
    创建守护进程调度器
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置好的调度器实例
    """
    reader = ArxivReader(config_path)
    scheduler = ArxivScheduler(reader)
    return scheduler


def run_daemon(config_path: str = "config/config.yaml") -> None:
    """
    运行守护进程模式
    
    Args:
        config_path: 配置文件路径
    """
    scheduler = create_daemon_scheduler(config_path)
    
    try:
        scheduler.start()
        
        print("🚀 arXiv Reader 守护进程已启动")
        print(f"📅 每日执行时间: {scheduler.config.schedule.daily_time}")
        print(f"🌍 时区: {scheduler.config.schedule.timezone}")
        
        next_run = scheduler.get_next_run_time()
        if next_run:
            print(f"⏰ 下次运行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        print("按 Ctrl+C 停止守护进程")
        
        # 保持程序运行
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n🛑 收到停止信号，正在关闭...")
        scheduler.stop()
        print("✅ 守护进程已停止")
    
    except Exception as e:
        print(f"❌ 守护进程异常: {e}")
        scheduler.stop()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="arXiv Reader 调度器")
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--daemon", action="store_true", help="运行守护进程模式")
    parser.add_argument("--test", action="store_true", help="测试调度配置")
    parser.add_argument("--status", action="store_true", help="显示调度器状态")
    parser.add_argument("--run-now", action="store_true", help="立即运行一次任务")
    
    args = parser.parse_args()
    
    if args.daemon:
        run_daemon(args.config)
    else:
        scheduler = create_daemon_scheduler(args.config)
        
        if args.test:
            result = scheduler.test_schedule()
            print("调度配置测试结果:")
            print(f"  配置有效: {'✅' if result['config_valid'] else '❌'}")
            print(f"  时区有效: {'✅' if result['timezone_valid'] else '❌'}")
            print(f"  时间格式有效: {'✅' if result['time_format_valid'] else '❌'}")
            
            if result["errors"]:
                print("错误:")
                for error in result["errors"]:
                    print(f"  - {error}")
        
        elif args.status:
            status = scheduler.get_status()
            print("调度器状态:")
            print(f"  启用状态: {'✅' if status['enabled'] else '❌'}")
            print(f"  运行状态: {'✅' if status['running'] else '❌'}")
            print(f"  每日时间: {status['daily_time']}")
            print(f"  时区: {status['timezone']}")
            print(f"  下次运行: {status['next_run_time'] or '未安排'}")
            print(f"  上次运行: {status['last_run_time'] or '从未运行'}")
            print(f"  上次结果: {'✅ 成功' if status['last_run_success'] else '❌ 失败' if status['last_run_success'] is False else '未知'}")
        
        elif args.run_now:
            print("🚀 立即运行任务...")
            result = scheduler.run_now()
            
            if result["success"]:
                print("✅ 任务执行成功")
                print(f"  获取论文: {result.get('papers_fetched', 0)} 篇")
                print(f"  翻译论文: {result.get('papers_translated', 0)} 篇")
                print(f"  邮件发送: {'成功' if result.get('email_sent') else '失败'}")
            else:
                print("❌ 任务执行失败")
                for error in result.get("errors", []):
                    print(f"  错误: {error}")
        
        else:
            print("请指定操作: --daemon, --test, --status 或 --run-now")
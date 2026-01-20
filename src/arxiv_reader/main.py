"""
主程序模块
负责整合获取、翻译、发送流程
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config import load_config
from .arxiv_fetcher import ArxivFetcher
from .translator import GPTTranslator
from .email_sender import EmailSender
from .storage import PaperStorage, PaperData


def setup_logging(log_file: str, level: str, console_output: bool) -> None:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers = [logging.FileHandler(log_file, encoding="utf-8")]
    if console_output:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


class ArxivReader:
    """arXiv Reader 主流程"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        self.config.create_directories()
        setup_logging(
            self.config.logging.log_file,
            self.config.logging.level,
            self.config.logging.console_output,
        )

        self.logger = logging.getLogger(__name__)
        self.storage = PaperStorage(self.config)
        self.fetcher = ArxivFetcher(self.config, self.storage)
        self.translator = GPTTranslator(self.config, self.storage)
        self.email_sender = EmailSender(self.config)

    def test_connections(self) -> Dict[str, bool]:
        results = {
            "arxiv": self.fetcher.test_connection(),
            "gpt": self.translator.test_connection(),
            "email": self.email_sender.test_email_connection(),
        }
        return results

    def _flatten_papers(
        self, papers_by_category: Dict[str, List[PaperData]]
    ) -> List[PaperData]:
        papers: List[PaperData] = []
        for category_papers in papers_by_category.values():
            papers.extend(category_papers)
        return papers

    def run_once(self, debug: bool = False) -> Dict[str, Any]:
        self.logger.info("=" * 50)
        self.logger.info(f"开始执行每日流程 (debug={debug})")
        self.logger.info("=" * 50)

        start_time = time.time()
        results: Dict[str, Any] = {
            "start_time": datetime.now().isoformat(),
            "success": False,
            "not_today": False,  # arXiv 页面日期不是今天
            "listing_date": None,  # arXiv 页面显示的日期
            "papers_fetched": 0,
            "papers_translated": 0,
            "email_sent": False,
            "errors": [],
        }

        try:
            fetch_result = self.fetcher.fetch_daily_papers(skip_date_check=debug)
            results["listing_date"] = (
                str(fetch_result.listing_date) if fetch_result.listing_date else None
            )

            # 如果 arXiv 页面日期不是今天且未启用 debug 模式，直接返回
            if not fetch_result.is_today and not debug:
                results["not_today"] = True
                self.logger.warning("arXiv 页面日期不是今天，跳过后续流程")
                return results

            papers_by_category = fetch_result.papers_by_category
            total_papers = fetch_result.total_papers
            results["papers_fetched"] = total_papers

            if total_papers == 0:
                self.logger.info("没有获取到论文，跳过翻译和邮件发送")
                results["success"] = True
                return results

            papers = self._flatten_papers(papers_by_category)
            translated, failed = self.translator.translate_papers(papers)
            results["papers_translated"] = translated
            if failed:
                self.logger.warning(f"翻译失败 {failed} 篇论文")

            # 翻译后重新保存 daily JSON（包含翻译结果）
            if translated > 0:
                self.storage.save_daily_papers(papers_by_category)

            favorite_papers = self.translator.filter_favorites(papers)
            if favorite_papers:
                self.logger.info(f"关注论文匹配到 {len(favorite_papers)} 篇")

            results["email_sent"] = self.email_sender.send_email(
                papers_by_category,
                favorite_papers=favorite_papers,
            )
            if not results["email_sent"]:
                results["errors"].append("邮件发送失败")

            self.storage.cleanup_old_data()
            results["success"] = results["email_sent"]

        except Exception as exc:
            error_msg = f"流程执行失败: {exc}"
            self.logger.error(error_msg)
            results["errors"].append(error_msg)

        finally:
            elapsed_time = time.time() - start_time
            results["end_time"] = datetime.now().isoformat()
            results["elapsed_time"] = elapsed_time
            self.logger.info("=" * 50)
            self.logger.info(f"流程结束，耗时 {elapsed_time:.2f} 秒")
            self.logger.info("=" * 50)

        return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="arXiv Reader - 定时获取、翻译并推送论文"
    )
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    parser.add_argument(
        "--debug", action="store_true", help="调试模式：跳过日期检查，强制获取论文"
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--daemon", action="store_true", help="启动定时守护模式")
    mode_group.add_argument("--run-once", action="store_true", help="立即运行一次流程")
    mode_group.add_argument("--test", action="store_true", help="测试外部服务连接")

    args = parser.parse_args()

    if not Path(args.config).exists():
        print(f"❌ 配置文件不存在: {args.config}")
        return 1

    if args.daemon:
        from .scheduler import run_daemon

        run_daemon(args.config)
        return 0

    try:
        reader = ArxivReader(args.config)
    except Exception as exc:
        print(f"❌ 配置加载失败: {exc}")
        return 1

    if args.test:
        results = reader.test_connections()
        print("连接测试结果:")
        for name, ok in results.items():
            status = "✅ 成功" if ok else "❌ 失败"
            print(f"  {name}: {status}")
        return 0

    if args.run_once or (not args.daemon and not args.test):
        results = reader.run_once(debug=args.debug)

        if results.get("not_today"):
            print(
                f"⏳ arXiv 页面日期 ({results.get('listing_date')}) 不是今天，跳过执行"
            )
            print(f"  耗时: {results['elapsed_time']:.2f} 秒")
            return 0

        if results["success"]:
            print("✅ 流程执行成功")
            print(f"  获取论文: {results['papers_fetched']} 篇")
            print(f"  翻译论文: {results['papers_translated']} 篇")
            print(f"  邮件发送: {'成功' if results['email_sent'] else '失败'}")
            print(f"  耗时: {results['elapsed_time']:.2f} 秒")
            return 0

        print("❌ 流程执行失败")
        for error in results["errors"]:
            print(f"  错误: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
主程序模块
把抓取和翻译串起来，并提供命令行入口
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .arxiv_fetcher import ArxivFetcher, ListingNotReady
from .config import load_config
from .pipeline import Pipeline
from .storage import PaperStorage
from .translator import GPTTranslator


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
    # requests / openai 的调试日志太吵
    for noisy in ("urllib3", "httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class ArxivReader:
    """arXiv Reader 主流程"""

    def __init__(
        self,
        config_path: str = "config/config.yaml",
        data_dir: Optional[str] = None,
        use_llm: bool = True,
    ):
        self.config = load_config(config_path)
        if data_dir:
            self.config.storage.data_dir = data_dir
        self.config.create_directories()
        setup_logging(
            self.config.logging.log_file,
            self.config.logging.level,
            self.config.logging.console_output,
        )

        self.logger = logging.getLogger(__name__)
        self.storage = PaperStorage(self.config)
        self.fetcher = ArxivFetcher(self.config)
        self.translator = GPTTranslator(self.config, self.storage)
        self.pipeline = Pipeline(
            self.config,
            self.storage,
            self.fetcher,
            self.translator,
            use_llm=use_llm,
        )

    def test_connections(self) -> Dict[str, bool]:
        try:
            arxiv_ok = self.fetcher.peek_listing_date() is not None
        except Exception:
            arxiv_ok = False
        return {
            "arxiv": arxiv_ok,
            "gpt": self.translator.test_connection(),
        }

    def run_once(self, force: bool = False) -> Dict[str, Any]:
        self.logger.info("=" * 50)
        self.logger.info(f"开始处理当前的 arXiv 公告 (force={force})")
        result = self.pipeline.run(force=force)
        self.logger.info(f"处理结果: {result}")
        self.logger.info("=" * 50)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="arXiv Reader - 获取、翻译并推送每天的 arXiv 论文"
    )
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--daemon", action="store_true", help="启动守护进程（轮询列表页）"
    )
    mode_group.add_argument(
        "--run-once", action="store_true", help="立即处理当前的公告"
    )
    mode_group.add_argument("--test", action="store_true", help="测试外部服务连接")

    parser.add_argument(
        "--force",
        action="store_true",
        help="当前公告已经处理完也重新处理",
    )
    parser.add_argument(
        "--no-llm", action="store_true", help="试跑：不翻译，也不标成已完成"
    )
    parser.add_argument("--data-dir", help="换一个数据目录（试跑时用，避免碰正式数据）")

    args = parser.parse_args()

    if not Path(args.config).exists():
        print(f"❌ 配置文件不存在: {args.config}")
        return 1

    if args.daemon:
        if args.no_llm or args.data_dir or args.force:
            print("❌ 守护模式不支持试跑参数")
            return 1
        from .scheduler import run_daemon

        run_daemon(args.config)
        return 0

    force = args.force
    try:
        reader = ArxivReader(
            args.config,
            data_dir=args.data_dir,
            use_llm=not args.no_llm,
        )
    except Exception as exc:
        print(f"❌ 配置加载失败: {exc}")
        return 1

    if args.test:
        print("连接测试结果:")
        for name, ok in reader.test_connections().items():
            print(f"  {name}: {'✅ 成功' if ok else '❌ 失败'}")
        return 0

    try:
        result = reader.run_once(force=force)
    except ListingNotReady as exc:
        print(f"⏳ 列表页还没全部更新: {exc}")
        return 0

    if result.get("skipped"):
        print(f"⏭  {result['listing_date']} 已经处理过（加 --force 重新处理）")
        return 0
    print(f"{'✅' if not result['errors'] else '⚠️'} {result['listing_date']}")
    print(
        f"  论文: {result['papers']} 篇，新翻译 {result['translated']} 篇，失败 {result['translate_failed']} 篇"
    )
    for error in result["errors"]:
        print(f"  错误: {error}")
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

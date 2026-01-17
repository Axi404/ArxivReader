#!/usr/bin/env python3
"""
arXiv Reader 主启动脚本
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from arxiv_reader.main import main


if __name__ == "__main__":
    raise SystemExit(main())

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arxiv_reader.config import Config  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "list_cs_RO_new.html").read_text(encoding="utf-8")


@pytest.fixture
def config(tmp_path) -> Config:
    cfg = Config()
    cfg.arxiv.categories = ["cs.RO", "cs.CV"]
    cfg.storage.data_dir = str(tmp_path / "data")
    cfg.storage.retention_days = 0
    cfg.misc.request_delay = 0
    cfg.misc.max_retries = 0
    cfg.logging.log_file = str(tmp_path / "logs" / "test.log")
    return cfg

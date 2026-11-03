import json
import os
from datetime import datetime, timedelta

from arxiv_reader.config import Config
from arxiv_reader.storage import DailyListing, PaperData, PaperStorage


def legacy_daily():
    paper = {
        "arxiv_id": "2610.00001",
        "title": "Old paper",
        "authors": ["A"],
        "abstract": "x",
        "published": "2026-10-01T00:00:00+00:00",
        "categories": ["cs.RO"],
        "arxiv_url": "https://arxiv.org/abs/2610.00001",
        "pdf_url": "https://arxiv.org/pdf/2610.00001.pdf",
        "title_zh": "旧论文",
        "abstract_zh": "旧",
        "hjfy_url": "https://hjfy.top/arxiv/2610.00001",
        "fetched_at": "2026-10-02T02:00:00",
        "translated_at": "2026-10-02T02:05:00",
    }
    return {
        "date": "2026-10-02",
        "total_papers": 1,
        "categories": ["cs.RO"],
        "papers_by_category": {"cs.RO": [paper]},
        "generated_at": "2026-10-02T02:06:00",
    }


def test_legacy_daily_file_is_done_and_all_new(config):
    listing = DailyListing.from_dict(legacy_daily())
    assert listing.legacy and listing.done
    assert listing.kind_of("cs.RO", "2610.00001") == "new"
    assert listing.counts() == {"cs.RO": {"new": 1, "cross": 0}}


def test_paper_from_dict_ignores_unknown_fields():
    data = dict(
        legacy_daily()["papers_by_category"]["cs.RO"][0], kind="cross", whatever=1
    )
    paper = PaperData.from_dict(data)
    assert paper.arxiv_id == "2610.00001" and paper.is_translated()
    assert paper.comments is None and paper.primary_category is None


def test_atomic_write_and_last_done(config, tmp_path):
    storage = PaperStorage(config)
    (storage.daily_dir / "2026-10-02.json").write_text(
        json.dumps(legacy_daily()), encoding="utf-8"
    )
    assert storage.last_done_date() == "2026-10-02"

    listing = DailyListing(date="2026-10-05", status={"fetched_at": "x"})
    storage.save_daily(listing)
    assert not list(storage.daily_dir.glob(".*.tmp"))
    # 新的那天还没走完，最近完成的还是 10-02
    assert storage.last_done_date() == "2026-10-02"
    storage.save_state({"last_done": "2026-10-05"})
    assert storage.last_done_date() == "2026-10-05"
    assert storage.list_dates() == ["2026-10-05", "2026-10-02"]


# ---- 自动删除旧数据：默认关闭，配置里打开才删 ----


def _day(days_ago: int) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _old_files(storage):
    old_daily = storage.daily_dir / f"{_day(40)}.json"
    new_daily = storage.daily_dir / f"{_day(5)}.json"
    odd_name = storage.daily_dir / "2026-05-05-.json"
    old_paper = storage.papers_dir / "2601.00001.json"
    new_paper = storage.papers_dir / "2611.00001.json"
    for path in (old_daily, new_daily, odd_name, old_paper, new_paper):
        path.write_text("{}", encoding="utf-8")
    stamp = (datetime.now() - timedelta(days=40)).timestamp()
    os.utime(old_paper, (stamp, stamp))
    return old_daily, new_daily, odd_name, old_paper, new_paper


def test_cleanup_is_off_by_default(config):
    assert config.storage.retention_enabled is False
    config.storage.retention_days = 30
    storage = PaperStorage(config)
    files = _old_files(storage)
    storage.cleanup_old_data()
    assert all(path.exists() for path in files)


def test_cleanup_deletes_old_data_when_enabled(config):
    config.storage.retention_enabled = True
    config.storage.retention_days = 30
    storage = PaperStorage(config)
    old_daily, new_daily, odd_name, old_paper, new_paper = _old_files(storage)
    storage.cleanup_old_data()
    assert not old_daily.exists() and not old_paper.exists()
    assert new_daily.exists() and new_paper.exists()
    assert odd_name.exists()  # 文件名不是日期的不动


def test_cleanup_needs_positive_days(config):
    config.storage.retention_enabled = True
    config.storage.retention_days = 0
    storage = PaperStorage(config)
    files = _old_files(storage)
    storage.cleanup_old_data()
    assert all(path.exists() for path in files)


def test_retention_switch_in_config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("storage:\n  retention_days: 300\n", encoding="utf-8")
    cfg = Config.from_yaml(str(path), validate=False)
    assert cfg.storage.retention_enabled is False and cfg.storage.retention_days == 300
    path.write_text(
        "storage:\n  retention_enabled: true\n  retention_days: 300\n", encoding="utf-8"
    )
    assert Config.from_yaml(str(path), validate=False).storage.retention_enabled is True

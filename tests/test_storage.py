import json

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

import json

import pytest
from fastapi.testclient import TestClient

from arxiv_reader import web_server
from arxiv_reader.storage import DailyListing, PaperData, PaperStorage
from test_storage import legacy_daily


def make_paper(arxiv_id, title, primary="cs.RO"):
    return PaperData(
        arxiv_id=arxiv_id,
        title=title,
        authors=["Alice", "Bob"],
        abstract=f"Abstract of {arxiv_id}",
        published="2026-11-03",
        categories=[primary, "cs.RO"],
        arxiv_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        title_zh="中文标题",
        abstract_zh="中文摘要",
        primary_category=primary,
        comments="8 pages",
    )


@pytest.fixture
def client(config, tmp_path):
    storage = PaperStorage(config)
    (storage.daily_dir / "2026-10-30.json").write_text(
        json.dumps(legacy_daily() | {"date": "2026-10-30"}), encoding="utf-8"
    )
    listing = DailyListing(date="2026-11-03", status={"done_at": "x"})
    listing.papers_by_category = {
        "cs.RO": [
            make_paper("2611.00001", "A robot"),
            make_paper("2611.00231", "Cross from systems", primary="eess.SY"),
        ],
        "cs.CV": [make_paper("2611.00482", "Vision paper", primary="cs.CV")],
    }
    listing.kinds = {
        "cs.RO": {"2611.00001": "new", "2611.00231": "cross"},
        "cs.CV": {"2611.00482": "new"},
    }
    storage.save_daily(listing)
    for paper in listing.unique_papers():
        storage.save_paper(paper)

    cfg_file = tmp_path / "web.yaml"
    cfg_file.write_text(
        "arxiv:\n  categories: [cs.RO, cs.CV]\nstorage:\n  data_dir: '%s'\n"
        % config.storage.data_dir,
        encoding="utf-8",
    )
    web_server.app.state.config_path = str(cfg_file)
    with TestClient(web_server.app) as c:
        yield c


def test_no_html_pages(client):
    # 网页由 web/ 的静态文件提供，后端只有 /api
    assert client.get("/").status_code == 404
    assert client.get("/daily/2026-11-03").status_code == 404


def test_dates(client):
    assert client.get("/api/dates").json()["dates"] == ["2026-11-03", "2026-10-30"]


def test_overview_counts_per_category_entry(client):
    data = client.get("/api/overview").json()
    assert [d["date"] for d in data["days"]] == ["2026-11-03", "2026-10-30"]
    latest = data["days"][0]["summary"]
    assert latest["new"] == 2 and latest["cross"] == 1 and latest["translated"] == 3
    ro = next(c for c in latest["categories"] if c["code"] == "cs.RO")
    assert ro == {"code": "cs.RO", "translated": 2, "new": 1, "cross": 1}
    assert data["stats"] == {"days": 2, "papers": 3}


def test_visit_is_counted(client):
    before = client.get("/api/overview").json()["traffic"]["total"]
    assert client.post("/api/visit").json() == {"ok": True}
    assert client.get("/api/overview").json()["traffic"]["total"] == before + 1


def test_daily_raw_and_filters(client):
    raw = client.get("/api/daily/2026-11-03").json()
    assert raw["format"] == 2 and raw["counts"]["cs.RO"] == {"new": 1, "cross": 1}
    cross = client.get(
        "/api/daily/2026-11-03", params={"category": "cs.RO", "kind": "cross"}
    ).json()
    assert [p["arxiv_id"] for p in cross["papers_by_category"]["cs.RO"]] == [
        "2611.00231"
    ]
    assert cross["categories"] == ["cs.RO"] and cross["total_papers"] == 1
    legacy_new = client.get("/api/daily/2026-10-30", params={"kind": "new"}).json()
    assert len(legacy_new["papers_by_category"]["cs.RO"]) == 1
    assert client.get("/api/daily/2026-11-03", params={"kind": "bad"}).status_code == 422
    assert client.get("/api/daily/2099-01-01").status_code == 404
    assert client.get("/api/daily/..%2F..%2Fetc").status_code == 404


def test_paper_and_search(client):
    assert client.get("/api/paper/2611.00001").json()["title_zh"] == "中文标题"
    assert client.get("/api/paper/nope").status_code == 404
    assert client.get("/api/search", params={"q": "vision"}).json()["total"] == 1

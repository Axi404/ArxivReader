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
            make_paper("2611.00001", "A <script>alert(1)</script> robot"),
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


def test_index_lists_dates(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "2026-11-03" in r.text and 'href="/daily/2026-11-03"' in r.text
    assert "2026 年 10 月" in r.text and "2026 年 11 月" in r.text


def test_daily_page_new_format(client):
    r = client.get("/daily/2026-11-03")
    assert r.status_code == 200
    html = r.text
    assert 'id="cat-cs-RO"' in html and 'id="cat-cs-CV"' in html
    assert 'id="cat-cs-RO-cross"' in html and "eess.SY" in html
    assert 'data-pref="scope"' in html and 'id="calPop"' in html
    assert "关注" not in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert 'href="/daily/2026-10-30"' in html  # 前一期


def test_daily_page_legacy_format(client):
    r = client.get("/daily/2026-10-30")
    assert r.status_code == 200
    assert "Old paper" in r.text and "旧论文" in r.text


def test_daily_page_missing(client):
    assert client.get("/daily/2099-01-01").status_code == 404
    assert client.get("/daily/..%2F..%2Fetc").status_code == 404


def test_api(client):
    assert client.get("/api/dates").json()["dates"] == ["2026-11-03", "2026-10-30"]
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
    assert (
        client.get("/api/daily/2026-11-03", params={"kind": "bad"}).status_code == 422
    )
    assert client.get("/api/paper/2611.00001").json()["title_zh"] == "中文标题"
    assert client.get("/api/search", params={"q": "vision"}).json()["total"] == 1


def test_static_assets(client):
    r = client.get("/static/web.css")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert client.get("/static/web.js").status_code == 200


def test_linkify_escapes_and_links():
    html = str(web_server.linkify("see https://a.b/c?x=1&y=2). <b>x</b>"))
    assert '<a href="https://a.b/c?x=1&amp;y=2"' in html and "</a>)." in html
    assert "<b>" not in html and "&lt;b&gt;" in html


def test_detex_only_touches_common_escapes():
    assert (
        web_server.detex(r"from 6.0\% to \emph{24}~ms, $x_1$")
        == "from 6.0% to 24\u00a0ms, $x_1$"
    )

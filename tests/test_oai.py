from datetime import date
from pathlib import Path

import pytest

from arxiv_reader.arxiv_fetcher import ArxivFetcher
from arxiv_reader.oai import oai_set_for, parse_oai_page, split_authors

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_page_keeps_versions_and_cleans_text():
    records, token, error = parse_oai_page(page("oai_arxivraw_page1.xml"))
    assert error is None and token == "token-page-2"
    ids = [r.arxiv_id for r in records]
    assert ids == [
        "2611.20001",
        "2611.20002",
        "2611.10003",
        "0805.0747",
    ]  # 删除的记录不要
    first = records[0]
    assert first.title == "A New Robot Policy"
    assert first.abstract == "We study robots. Line two."
    assert first.authors == ["Ada Lovelace", "Alan Turing", "Grace Hopper"]
    assert first.categories == ["cs.RO", "cs.LG"] and first.primary_category == "cs.RO"
    assert first.comments == "8 pages" and first.journal_ref is None
    assert records[1].journal_ref == "CoRL 2026"


def test_new_submissions_are_v1_only_and_recent():
    records, _, _ = parse_oai_page(page("oai_arxivraw_page1.xml"))
    new = {r.arxiv_id: r.is_new_submission() for r in records}
    assert new == {
        "2611.20001": True,
        "2611.20002": True,
        "2611.10003": False,  # 有 v2：replacement
        "0805.0747": False,  # 只有 v1，但是 2008 年的：改了元数据或者新加了分类
    }


def test_no_records_match_is_not_an_error():
    xml = (
        '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        '<error code="noRecordsMatch">empty</error></OAI-PMH>'
    )
    assert parse_oai_page(xml) == ([], None, None)
    bad = xml.replace("noRecordsMatch", "badResumptionToken")
    assert parse_oai_page(bad)[2] == "badResumptionToken"


def test_helpers():
    assert split_authors("A B,  C D and E F") == ["A B", "C D", "E F"]
    assert split_authors("") == []
    assert oai_set_for("cs.RO") == "cs" and oai_set_for("eess.SY") == "eess"
    assert oai_set_for("hep-th") == "physics:hep-th"


def test_fetch_oai_groups_by_announcement_day(config):
    config.arxiv.include_cross_lists = ["cs.RO"]
    urls = []

    def get(url):
        urls.append(url)
        return page(
            "oai_arxivraw_page2.xml"
            if "resumptionToken" in url
            else "oai_arxivraw_page1.xml"
        )

    fetcher = ArxivFetcher(config, get=get, sleep=lambda s: None)
    results = fetcher.fetch_oai(date(2026, 11, 16))
    # cs.RO 和 cs.CV 都在 set=cs 里，一个 set 只请求一遍（两页）
    assert len(urls) == 2
    assert (
        "metadataPrefix=arXivRaw" in urls[0]
        and "set=cs" in urls[0]
        and "from=2026-11-16" in urls[0]
    )
    assert "until=" not in urls[0]
    assert [r.listing_date for r in results] == [date(2026, 11, 16), date(2026, 11, 17)]
    assert all(r.source == "oai" for r in results)

    monday, tuesday = results
    assert [e.arxiv_id for e in monday.pages["cs.RO"].entries] == ["2611.19990"]
    ro = tuesday.pages["cs.RO"]
    assert [(e.arxiv_id, e.kind) for e in ro.entries] == [
        ("2611.20001", "new"),
        ("2611.20002", "cross"),
    ]
    cv = tuesday.pages["cs.CV"]
    assert [(e.arxiv_id, e.kind) for e in cv.entries] == [("2611.20002", "new")]
    assert cv.entries[0].categories == ["cs.CV", "cs.RO"]
    assert ro.header_counts == {"new": None, "cross": None, "replace": None}


def test_fetch_oai_respects_cross_list_setting_and_until(config):
    config.arxiv.include_cross_lists = False
    urls = []

    def get(url):
        urls.append(url)
        return page(
            "oai_arxivraw_page2.xml"
            if "resumptionToken" in url
            else "oai_arxivraw_page1.xml"
        )

    fetcher = ArxivFetcher(config, get=get, sleep=lambda s: None)
    results = fetcher.fetch_oai(date(2026, 11, 17), date(2026, 11, 17))
    assert "until=2026-11-17" in urls[0]
    tuesday = [r for r in results if r.listing_date == date(2026, 11, 17)][0]
    assert [e.arxiv_id for e in tuesday.pages["cs.RO"].entries] == ["2611.20001"]


def test_fetch_oai_raises_on_oai_error(config):
    xml = (
        '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        '<error code="badArgument">nope</error></OAI-PMH>'
    )
    fetcher = ArxivFetcher(config, get=lambda url: xml, sleep=lambda s: None)
    with pytest.raises(RuntimeError):
        fetcher.fetch_oai(date(2026, 11, 17))

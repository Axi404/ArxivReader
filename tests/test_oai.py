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


def _rec(arxiv_id, stamp, *v_dates, cats=("cs.RO",)):
    from datetime import datetime, timezone

    from arxiv_reader.oai import OaiRecord

    return OaiRecord(
        arxiv_id=arxiv_id,
        datestamp=date.fromisoformat(stamp),
        versions=[
            datetime.fromisoformat(d).replace(tzinfo=timezone.utc) for d in v_dates
        ],
        title=arxiv_id,
        abstract="a",
        categories=list(cats),
    )


def test_grouping_by_id_ranges_keeps_papers_redated_after_announcement():
    from arxiv_reader.oai import group_new_submissions

    records = [
        # 11-13 的论文，11-16 改了元数据：编号在上一天以内，不算
        _rec("2611.15781", "2026-11-16", "2026-11-11"),
        # 11-16 公告的
        _rec("2611.17338", "2026-11-16", "2026-11-13"),
        _rec("2611.18562", "2026-11-16", "2026-11-13"),
        # 11-16 公告、当天又交了 v2（11-17 公告），datestamp 已经是 11-17
        _rec("2611.17442", "2026-11-17", "2026-11-12", "2026-11-16"),
        # 11-17 公告的；第一篇 v1 是 8 月的（被 hold 了几个月）
        _rec("2611.18583", "2026-11-17", "2026-08-05", cats=("cs.CL",)),
        _rec("2611.19001", "2026-11-17", "2026-11-16"),
        # 11-13 的论文 11-17 换了版本：replacement
        _rec("2611.16000", "2026-11-17", "2026-11-12", "2026-11-16"),
        # 老论文 11-17 新 cross-list 到 cs.RO：分不出来，等列表页补
        _rec("2611.16162", "2026-11-17", "2026-11-12", cats=("cs.CV", "cs.RO")),
    ]
    groups = group_new_submissions(records, after_id="2611.17336")
    got = {d.isoformat(): [r.arxiv_id for r in v] for d, v in groups.items()}
    assert got == {
        "2026-11-16": ["2611.17338", "2611.17442", "2611.18562"],
        "2026-11-17": ["2611.18583", "2611.19001"],
    }
    # 没有上一天的编号时退回去看 v1 的日期：会漏掉被 hold 的和公告后换了版本的
    got = {
        d.isoformat(): [r.arxiv_id for r in v]
        for d, v in group_new_submissions(records).items()
    }
    assert got == {
        "2026-11-16": ["2611.15781", "2611.17338", "2611.18562"],
        "2026-11-17": ["2611.16162", "2611.19001"],
    }


def test_max_arxiv_id_ignores_old_style_ids():
    from arxiv_reader.oai import max_arxiv_id

    assert (
        max_arxiv_id(["2611.9999", "2611.18562", "cs/0702142", "2610.99999"])
        == "2611.18562"
    )
    assert max_arxiv_id(["cs/0702142"]) is None


@pytest.mark.parametrize(
    "tex, plain",
    [
        ("S\\'ebastien Pi\\'erard", "Sébastien Piérard"),
        ("Jo\\~ao", "João"),
        ("H{\\aa}kan", "Håkan"),
        ('Baran C\\"ur\\"ukl\\"u', "Baran Cürüklü"),
        ("Fran\\c{c}ois", "François"),
        ("{\\v S}imon", "Šimon"),
        ("Bj{\\o}rn", "Bjørn"),
        ("Bj\\o rn", "Bjørn"),
        ("\\'{E}lise", "Élise"),
        ("{\\'E}lise", "Élise"),
        ("Mart\\'{\\i}n", "Martín"),
        ("Mart\\'\\i n", "Martín"),
        ("Erd\\H{o}s", "Erdős"),
        ('{M\\"u}ller', "Müller"),
        ("Gro{\\ss}", "Groß"),
        ("J.~Smith", "J. Smith"),
        ("$\\omega$ and \\left", "$\\omega$ and \\left"),  # 不是重音的控制词不动
    ],
)
def test_tex_to_unicode(tex, plain):
    from arxiv_reader.oai import tex_to_unicode

    assert tex_to_unicode(tex) == plain


def test_split_authors_like_the_listing_page():
    # 2026-11-17 的几种写法；改完以后 702 篇里只有 4 篇和列表页不一样（都是列表页自己截断或者拆错）
    assert split_authors(
        "Jiaying Xu (Conamur), Zhen Dong (University of California, Santa Barbara)"
    ) == ["Jiaying Xu", "Zhen Dong"]
    assert split_authors("Chao Zhang, Huayan Pu, and Jinglei Zhao") == [
        "Chao Zhang",
        "Huayan Pu",
        "Jinglei Zhao",
    ]
    assert split_authors("Meituan LongCat Team: Xunliang Cai, Yiqi Chen") == [
        "Meituan LongCat Team",
        "Xunliang Cai",
        "Yiqi Chen",
    ]
    assert split_authors("Jelena Mitrovi\\'c and H{\\aa}kan Forsberg") == [
        "Jelena Mitrović",
        "Håkan Forsberg",
    ]


def test_batch_max_id_gallops_then_bisects(config):
    seen = []

    def status(url):
        seen.append(url)
        number = int(url.rsplit(".", 1)[1])
        return 200 if number <= 20107 else 404

    fetcher = ArxivFetcher(config, sleep=lambda s: None, status=status)
    assert fetcher.batch_max_id("2611.20029") == "2611.20107"
    assert all(u.startswith("https://arxiv.org/abs/2611.") for u in seen)
    assert len(seen) <= 16
    # 已经是最大的
    seen.clear()
    assert fetcher.batch_max_id("2611.20107") == "2611.20107"
    assert len(seen) == 1


def test_batch_max_id_gives_up_on_errors_and_odd_ids(config):
    fetcher = ArxivFetcher(config, sleep=lambda s: None, status=lambda url: None)
    assert fetcher.batch_max_id("2611.20029") is None
    assert fetcher.batch_max_id("cs/0702142") is None
    always = ArxivFetcher(config, sleep=lambda s: None, status=lambda url: 200)
    assert always.batch_max_id("2611.20029", max_requests=5) is None


def test_oai_has_record(config):
    def get(url):
        assert "verb=GetRecord" in url and "identifier=oai:arXiv.org:" in url
        if url.endswith("2611.20001"):
            return page("oai_arxivraw_page1.xml")
        return (
            '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
            '<error code="idDoesNotExist">no</error></OAI-PMH>'
        )

    fetcher = ArxivFetcher(config, get=get, sleep=lambda s: None)
    assert fetcher.oai_has_record("2611.20001", date(2026, 11, 17)) is True
    assert fetcher.oai_has_record("2611.20001", date(2026, 11, 18)) is False
    assert fetcher.oai_has_record("2611.29999", date(2026, 11, 17)) is False
    broken = ArxivFetcher(config, get=lambda url: "not xml", sleep=lambda s: None)
    assert broken.oai_has_record("2611.20001", date(2026, 11, 17)) is None

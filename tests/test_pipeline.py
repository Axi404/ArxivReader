import json

import pytest

from arxiv_reader.arxiv_fetcher import ArxivFetcher, FetchResult
from arxiv_reader.listing import parse_listing
from arxiv_reader.pipeline import Pipeline
from arxiv_reader.storage import PaperStorage


class FakeTranslator:
    def __init__(self, fail_ids=()):
        self.translated = []
        self.fail_ids = set(fail_ids)
        self.boom = False

    def translate_papers(self, papers):
        if self.boom:
            raise RuntimeError("模型挂了")
        ok = 0
        for p in papers:
            if p.arxiv_id in self.fail_ids:
                continue
            p.set_translation("中文" + p.arxiv_id, "摘要" + p.arxiv_id)
            self.translated.append(p.arxiv_id)
            ok += 1
        return ok, len(papers) - ok


def make_fetched(listing_html):
    ro = parse_listing(listing_html, "cs.RO")
    # cs.CV 页面：把 cs.RO 里那篇 cs.CV 主类的 cross-list 当作 cs.CV 的新提交
    cv = parse_listing(listing_html, "cs.CV")
    cv.entries = [e for e in cv.entries if e.arxiv_id == "2611.00482"]
    for e in cv.entries:
        e.kind = "new"
    cv.header_counts = {"new": 1, "cross": 0, "replace": 0}
    return FetchResult(listing_date=ro.listing_date, pages={"cs.RO": ro, "cs.CV": cv})


@pytest.fixture
def parts(config, listing_html):
    storage = PaperStorage(config)
    fetched = make_fetched(listing_html)
    fetcher = ArxivFetcher(config, get=lambda url: "")
    fetcher.fetch_all = lambda categories=None: fetched
    return config, storage, fetcher


def test_full_run_is_idempotent(parts):
    config, storage, fetcher = parts
    translator = FakeTranslator()
    pipeline = Pipeline(config, storage, fetcher, translator)

    first = pipeline.run()
    assert first["done"] and first["listing_date"] == "2026-11-03"
    assert (
        first["papers"] == 6
    )  # 4 + 2 条 cross，其中一条也是 cs.CV 的新提交，去重后 6 篇

    data = json.loads(storage.daily_path("2026-11-03").read_text(encoding="utf-8"))
    assert data["format"] == 2 and data["status"]["done_at"]
    kinds = {p["arxiv_id"]: p["kind"] for p in data["papers_by_category"]["cs.RO"]}
    assert kinds["2611.00231"] == "cross" and kinds["2611.00155"] == "new"
    assert data["counts"]["cs.RO"] == {"new": 4, "cross": 2}
    assert storage.load_state()["last_done"] == "2026-11-03"

    saved = storage.load_paper("2611.00155")
    assert saved.comments.startswith("4 pages") and saved.announced == "2026-11-03"
    assert saved.title_zh == "中文2611.00155"

    translator.translated.clear()
    assert pipeline.run()["skipped"] == "already done"
    assert translator.translated == []


def test_a_paper_in_two_categories_is_translated_in_both(parts):
    """2611.00482 是 cs.CV 的新提交，同时是 cs.RO 的 cross-list：只翻译一次，两个分类里都要有中文"""
    config, storage, fetcher = parts
    translator = FakeTranslator()
    Pipeline(config, storage, fetcher, translator).run()
    assert translator.translated.count("2611.00482") == 1

    data = json.loads(storage.daily_path("2026-11-03").read_text(encoding="utf-8"))
    copies = [
        (category, p["kind"], p["title_zh"], p["abstract_zh"])
        for category, papers in data["papers_by_category"].items()
        for p in papers
        if p["arxiv_id"] == "2611.00482"
    ]
    assert copies == [
        ("cs.RO", "cross", "中文2611.00482", "摘要2611.00482"),
        ("cs.CV", "new", "中文2611.00482", "摘要2611.00482"),
    ]
    untranslated = [
        p["arxiv_id"]
        for papers in data["papers_by_category"].values()
        for p in papers
        if not (p["title_zh"] and p["abstract_zh"])
    ]
    assert untranslated == []


def test_rerun_fills_a_copy_left_untranslated(parts):
    """2026-11-04 的样子：只有 cs.RO 那一份有中文。--force 重跑以后两份都有，不用再调模型"""
    config, storage, fetcher = parts
    translator = FakeTranslator()
    pipeline = Pipeline(config, storage, fetcher, translator)
    pipeline.run()
    path = storage.daily_path("2026-11-03")
    data = json.loads(path.read_text(encoding="utf-8"))
    for p in data["papers_by_category"]["cs.CV"]:
        p["title_zh"] = p["abstract_zh"] = None
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    translator.translated.clear()
    assert pipeline.run(force=True)["done"]
    assert translator.translated == []
    fixed = json.loads(path.read_text(encoding="utf-8"))
    assert fixed["papers_by_category"]["cs.CV"][0]["title_zh"] == "中文2611.00482"


def test_crash_in_translation_resumes(parts):
    config, storage, fetcher = parts
    translator = FakeTranslator()
    translator.boom = True
    pipeline = Pipeline(config, storage, fetcher, translator)
    with pytest.raises(RuntimeError):
        pipeline.run()
    listing = storage.load_daily("2026-11-03")
    assert listing is not None and not listing.done and "fetched_at" in listing.status

    translator.boom = False
    assert pipeline.run()["done"]


def test_dry_run_does_not_mark_done(parts):
    config, storage, fetcher = parts
    result = Pipeline(config, storage, fetcher, None, use_llm=False).run()
    assert not result["done"]
    assert not storage.load_daily("2026-11-03").done
    assert "last_done" not in storage.load_state()


def test_keeps_translation_unless_text_changed(parts, listing_html):
    config, storage, fetcher = parts
    translator = FakeTranslator()
    Pipeline(config, storage, fetcher, translator).run(force=True)
    assert "2611.00155" in translator.translated

    translator.translated.clear()
    Pipeline(config, storage, fetcher, translator).run(force=True)
    assert translator.translated == []  # 都已经翻译过

    changed = make_fetched(
        listing_html.replace("Post-incident analysis", "Post-incident review")
    )
    fetcher.fetch_all = lambda categories=None: changed
    Pipeline(config, storage, fetcher, translator).run(force=True)
    assert translator.translated == ["2611.00155"]


def test_failed_translation_is_counted(parts):
    config, storage, fetcher = parts
    translator = FakeTranslator(fail_ids={"2611.00158"})
    result = Pipeline(config, storage, fetcher, translator).run()
    assert result["translate_failed"] == 1
    assert storage.load_daily("2026-11-03").status["translate_failed"] == 1


def test_backfilling_a_day_from_the_old_code_keeps_it_done(parts):
    from test_storage import legacy_daily

    config, storage, fetcher = parts
    old = legacy_daily() | {"date": "2026-11-03"}
    storage.daily_path("2026-11-03").write_text(json.dumps(old), encoding="utf-8")

    pipeline = Pipeline(config, storage, fetcher, FakeTranslator())
    assert pipeline.run()["skipped"] == "already done"
    # 补抓：重新处理，翻译缺的
    assert pipeline.run(force=True)["done"]
    listing = storage.load_daily("2026-11-03")
    assert not listing.legacy and listing.done
    assert listing.counts()["cs.RO"] == {"new": 4, "cross": 2}
    # 不调模型的补抓也保持已完成
    Pipeline(config, storage, fetcher, None, use_llm=False).run(force=True)
    assert storage.load_daily("2026-11-03").done


def test_same_text_ignores_tex_accents_and_urls():
    from arxiv_reader.pipeline import _same_text

    assert _same_text("cubic B\\'ezier curves", "cubic Bézier curves")
    assert _same_text("code at this https URL.", "code at https://a.b/c.")
    assert not _same_text("Post-incident analysis", "Post-incident review")

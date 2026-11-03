from datetime import date

from arxiv_reader.listing import parse_listing, parse_listing_date


def test_parses_date_counts_and_sections(listing_html):
    page = parse_listing(listing_html, "cs.RO")
    assert page.listing_date == date(2026, 11, 3)
    assert page.header_counts == {"new": 4, "cross": 2, "replace": 1}
    assert page.parsed_counts() == {"new": 4, "cross": 2}
    assert page.shortfall() == {}
    # 替换版本不收
    assert all(e.kind in ("new", "cross") for e in page.entries)


def test_entry_fields(listing_html):
    page = parse_listing(listing_html, "cs.RO")
    first = page.entries[0]
    assert first.arxiv_id == "2611.00155"
    assert first.title.startswith("From Concepts to Actual Causes")
    assert first.authors == ["Gihyuk Ko"]
    assert first.comments.startswith("4 pages, 1 figure")
    assert first.primary_category == "cs.RO"
    assert first.categories == ["cs.RO", "cs.AI"]
    assert first.abstract.startswith("Post-incident analysis")
    assert "Title:" not in first.title and "Comments:" not in (first.comments or "")


def test_cross_list_keeps_primary_first(listing_html):
    page = parse_listing(listing_html, "cs.RO")
    cross = {e.arxiv_id: e for e in page.by_kind("cross")}
    external = cross["2611.00231"]
    assert external.primary_category == "eess.SY"
    assert external.categories[0] == "eess.SY" and "cs.RO" in external.categories
    assert cross["2611.00482"].primary_category == "cs.CV"


def test_submitter_put_authors_in_abstract_is_kept_as_is(listing_html):
    # 2611.00978 的作者把作者名单填进了摘要，这是 arXiv 上的原样数据
    page = parse_listing(listing_html, "cs.RO")
    entry = next(e for e in page.entries if e.arxiv_id == "2611.00978")
    assert entry.complete
    assert entry.abstract.startswith("Hao Ren, Shuohan Chen")


def test_shortfall_when_header_promises_more(listing_html):
    html = listing_html.replace(
        "New submissions (showing 4 of 4 entries)",
        "New submissions (showing 4 of 6 entries)",
    )
    page = parse_listing(html, "cs.RO")
    assert page.shortfall() == {"new": 2}


def test_listing_date_missing():
    assert parse_listing_date("<html>nothing</html>") is None
    assert parse_listing("<html></html>", "cs.RO").entries == []


def test_cross_lists_can_be_limited_to_some_categories(config, listing_html):
    from arxiv_reader.arxiv_fetcher import ArxivFetcher

    config.arxiv.include_cross_lists = ["cs.RO"]
    fetcher = ArxivFetcher(config, get=lambda url: listing_html, sleep=lambda s: None)
    assert len(fetcher.fetch_listing("cs.RO").by_kind("cross")) == 2
    cv = fetcher.fetch_listing("cs.CV")
    assert cv.by_kind("cross") == [] and cv.shortfall() == {}
    config.arxiv.include_cross_lists = False
    assert fetcher.fetch_listing("cs.RO").by_kind("cross") == []


def test_max_results_only_truncates_new_submissions(config, listing_html):
    from arxiv_reader.arxiv_fetcher import ArxivFetcher

    config.arxiv.max_results_per_category = 2
    page = ArxivFetcher(
        config, get=lambda url: listing_html, sleep=lambda s: None
    ).fetch_listing("cs.RO")
    assert [e.arxiv_id for e in page.by_kind("new")] == ["2611.00155", "2611.00978"]
    assert len(page.by_kind("cross")) == 2


def test_this_https_url_is_replaced_by_the_real_link(listing_html):
    html = listing_html.replace(
        "Accepted at the Science of Physical AI Safety (SPAIS) Workshop at CoRL 2026",
        'Project page: <a href="https://example.org/proj" rel="external">this https URL</a>',
    )
    entry = parse_listing(html, "cs.RO").entries[0]
    assert entry.comments.endswith("Project page: https://example.org/proj")

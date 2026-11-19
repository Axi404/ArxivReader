from datetime import date, datetime, timezone

import pytest

from arxiv_reader.arxiv_fetcher import ListingNotReady
from arxiv_reader.scheduler import (
    ArxivScheduler,
    expected_announcement,
    next_listing_date,
)
from arxiv_reader.storage import DailyListing, PaperData, PaperStorage

UTC = timezone.utc


def test_next_listing_date_skips_weekend():
    assert next_listing_date(date(2026, 10, 30)) == date(2026, 11, 2)  # 周五 -> 周一
    assert next_listing_date(date(2026, 11, 2)) == date(2026, 11, 3)


def test_expected_announcement_follows_us_eastern_time():
    # 2026-11-01 美国结束夏令时：之后美东 20:00 = UTC 01:00，之前 = UTC 00:00
    assert expected_announcement(date(2026, 11, 3)) == datetime(
        2026, 11, 3, 1, 0, tzinfo=UTC
    )
    assert expected_announcement(date(2026, 11, 2)) == datetime(
        2026, 11, 2, 1, 0, tzinfo=UTC
    )
    assert expected_announcement(date(2026, 10, 30)) == datetime(
        2026, 10, 30, 0, 0, tzinfo=UTC
    )


class FakeFetcher:
    def __init__(self, dates):
        self.dates = list(dates)
        self.calls = 0

    def peek_listing_date(self):
        self.calls += 1
        return self.dates.pop(0) if len(self.dates) > 1 else self.dates[0]


class FakeReader:
    def __init__(self, config, storage, dates):
        self.config = config
        self.storage = storage
        self.fetcher = FakeFetcher(dates)
        self.runs = 0
        self.raise_not_ready = 0

    def run_once(self, force=False):
        self.runs += 1
        if self.raise_not_ready:
            self.raise_not_ready -= 1
            raise ListingNotReady("还没全部更新")
        listing = self.fetcher.dates[0].isoformat()
        self.storage.save_daily(DailyListing(date=listing, status={"done_at": "x"}))
        return {"listing_date": listing, "done": True}


@pytest.fixture
def reader(config):
    storage = PaperStorage(config)
    storage.save_daily(DailyListing(date="2026-11-02", status={"done_at": "x"}))
    return FakeReader(config, storage, [date(2026, 11, 2)])


def test_waits_until_expected_announcement_then_polls(reader):
    sched = ArxivScheduler(reader)
    assert sched.last_done == "2026-11-02"
    # 11-03 的列表预计 UTC 01:00 出来，00:55 开始看
    assert sched.tick(datetime(2026, 11, 3, 0, 30, tzinfo=UTC)) == "waiting"
    assert reader.fetcher.calls == 0
    assert sched.tick(datetime(2026, 11, 3, 0, 56, tzinfo=UTC)) == "not-yet"
    # 间隔没到不再请求
    assert sched.tick(datetime(2026, 11, 3, 1, 0, tzinfo=UTC)) == "interval"
    assert reader.fetcher.calls == 1


def test_runs_when_new_listing_appears_and_then_waits(reader):
    reader.fetcher.dates = [date(2026, 11, 2), date(2026, 11, 3)]
    sched = ArxivScheduler(reader)
    assert sched.tick(datetime(2026, 11, 3, 1, 0, tzinfo=UTC)) == "not-yet"
    assert sched.tick(datetime(2026, 11, 3, 1, 10, tzinfo=UTC)) == "done"
    assert reader.runs == 1 and sched.last_done == "2026-11-03"
    # 处理完以后等 11-04 的公告（UTC 11-04 01:00）
    assert sched.tick(datetime(2026, 11, 3, 9, 0, tzinfo=UTC)) == "waiting"


def test_listing_not_ready_is_retried(reader):
    reader.fetcher.dates = [date(2026, 11, 3)]
    reader.raise_not_ready = 1
    sched = ArxivScheduler(reader)
    assert sched.tick(datetime(2026, 11, 3, 1, 0, tzinfo=UTC)) == "not-ready"
    assert sched.tick(datetime(2026, 11, 3, 1, 10, tzinfo=UTC)) == "done"


def test_waits_over_the_weekend_without_polling(reader):
    reader.storage.save_daily(DailyListing(date="2026-10-30", status={"done_at": "x"}))
    reader.storage.daily_path("2026-11-02").unlink()
    reader.fetcher.dates = [date(2026, 10, 30)]
    sched = ArxivScheduler(reader)
    assert sched.last_done == "2026-10-30"
    # 周六晚上：在等周一的公告（美东周日 20:00），不请求列表页
    assert sched.tick(datetime(2026, 10, 31, 15, 0, tzinfo=UTC)) == "waiting"
    assert sched.tick(datetime(2026, 11, 2, 0, 50, tzinfo=UTC)) == "waiting"
    assert reader.fetcher.calls == 0
    assert sched.tick(datetime(2026, 11, 2, 0, 56, tzinfo=UTC)) == "not-yet"


# ---- 列表页卡住时的 OAI 兜底 ----

from arxiv_reader.arxiv_fetcher import FetchResult  # noqa: E402
from arxiv_reader.listing import ListingEntry, ListingPage  # noqa: E402


def oai_day(day, n=30):
    page = ListingPage(
        category="cs.RO",
        listing_date=day,
        header_counts={"new": None, "cross": None, "replace": None},
        entries=[
            ListingEntry(arxiv_id=f"2611.{20000 + i}", kind="new") for i in range(n)
        ],
    )
    return FetchResult(listing_date=day, pages={"cs.RO": page}, source="oai")


class FallbackFetcher(FakeFetcher):
    def __init__(self, dates, oai_days=()):
        super().__init__(dates)
        self.oai_days = list(oai_days)
        self.oai_calls = []
        self.after_ids = []
        # 这一批最大的编号（None：查不出来）和 OAI 上有没有它
        self.batch_max = None
        self.oai_has = True
        self.tail_checks = []

    def batch_max_id(self, start_id):
        self.tail_checks.append(start_id)
        return self.batch_max

    def oai_has_record(self, arxiv_id, day):
        return self.oai_has

    def fetch_oai(self, start, end=None, after_id=None):
        self.oai_calls.append((start, end))
        self.after_ids.append(after_id)
        return [
            d
            for d in self.oai_days
            if d.listing_date >= start and (end is None or d.listing_date <= end)
        ]


class FallbackReader(FakeReader):
    def __init__(self, config, storage, dates, oai_days=()):
        super().__init__(config, storage, dates)
        self.fetcher = FallbackFetcher(dates, oai_days)
        self.fetched_runs = []
        self.forced_fetched = []
        self.forced_runs = 0

    def run_once(self, force=False):
        if force:
            self.forced_runs += 1
        result = super().run_once(force)
        daily = self.storage.load_daily(result["listing_date"])
        daily.status["source"] = "listing"
        self.storage.save_daily(daily)
        return result

    def run_fetched(self, fetched, force=False):
        day = fetched.listing_date.isoformat()
        self.fetched_runs.append(day)
        if force:
            self.forced_fetched.append(day)
        papers = {
            c: [
                PaperData(
                    arxiv_id=e.arxiv_id,
                    title="t",
                    authors=[],
                    abstract="a",
                    published=day,
                    categories=[c],
                    arxiv_url="",
                    pdf_url="",
                )
                for e in page.entries
            ]
            for c, page in fetched.pages.items()
        }
        kinds = {
            c: {e.arxiv_id: e.kind for e in page.entries}
            for c, page in fetched.pages.items()
        }
        self.storage.save_daily(
            DailyListing(
                date=day,
                status={"done_at": "x", "source": "oai"},
                papers_by_category=papers,
                kinds=kinds,
            )
        )
        return {"listing_date": day, "done": True}


@pytest.fixture
def stuck(config):
    """11-16 处理完了，11-17 的列表页一直停在 11-16，OAI 上已经有 11-17"""
    storage = PaperStorage(config)
    storage.save_daily(DailyListing(date="2026-11-16", status={"done_at": "x"}))
    return FallbackReader(
        config, storage, [date(2026, 11, 16)], oai_days=[oai_day(date(2026, 11, 17))]
    )


def test_fallback_waits_three_hours_and_two_matching_reads(stuck):
    sched = ArxivScheduler(stuck)
    # 11-17 的公告预计 UTC 01:00；三小时以内只看列表页
    assert sched.tick(datetime(2026, 11, 17, 3, 50, tzinfo=UTC)) == "not-yet"
    assert stuck.fetcher.oai_calls == []
    # 04:00 第一次去 OAI：记下条数，先不处理
    assert sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC)) == "not-yet"
    assert stuck.fetcher.oai_calls == [(date(2026, 11, 17), None)]
    assert stuck.fetched_runs == []
    # 兜底间隔（30 分钟）没到，只看列表页
    assert sched.tick(datetime(2026, 11, 17, 4, 15, tzinfo=UTC)) == "not-yet"
    assert len(stuck.fetcher.oai_calls) == 1
    # 04:30 条数没变：处理 11-17
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "fallback"
    assert stuck.fetched_runs == ["2026-11-17"] and sched.last_done == "2026-11-17"


def test_fallback_waits_while_oai_is_still_growing(stuck):
    sched = ArxivScheduler(stuck)
    assert sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC)) == "not-yet"
    stuck.fetcher.oai_days = [oai_day(date(2026, 11, 17), n=40)]  # 还在索引
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "not-yet"
    assert stuck.fetched_runs == []
    assert sched.tick(datetime(2026, 11, 17, 5, 0, tzinfo=UTC)) == "fallback"


def test_listing_catching_up_reprocesses_the_oai_day(stuck):
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "fallback"
    # 下一次公告（11-18）之前也继续看列表页，因为 11-17 是 OAI 拼的
    assert sched.tick(datetime(2026, 11, 17, 4, 40, tzinfo=UTC)) == "not-yet"
    stuck.fetcher.dates = [date(2026, 11, 17)]
    assert sched.tick(datetime(2026, 11, 17, 7, 50, tzinfo=UTC)) == "reconciled"
    assert stuck.forced_runs == 1
    assert stuck.storage.load_daily("2026-11-17").status["source"] == "listing"
    # 过完一遍以后安静地等 11-18
    assert sched.tick(datetime(2026, 11, 17, 9, 0, tzinfo=UTC)) == "waiting"


def test_skipped_listing_day_is_filled_from_oai(config):
    storage = PaperStorage(config)
    storage.save_daily(DailyListing(date="2026-11-13", status={"done_at": "x"}))
    reader = FallbackReader(
        config,
        storage,
        [date(2026, 11, 13), date(2026, 11, 17)],
        oai_days=[oai_day(date(2026, 11, 16)), oai_day(date(2026, 11, 17))],
    )
    sched = ArxivScheduler(reader)
    assert sched.tick(datetime(2026, 11, 16, 1, 0, tzinfo=UTC)) == "not-yet"
    # 列表页从 11-13 直接跳到 11-17：先从 OAI 补 11-16，再按列表页处理 11-17
    assert sched.tick(datetime(2026, 11, 17, 1, 10, tzinfo=UTC)) == "done"
    assert reader.fetcher.oai_calls[-1] == (date(2026, 11, 16), None)
    assert reader.fetched_runs == ["2026-11-16"]
    assert sched.last_done == "2026-11-17"


def test_fallback_can_be_turned_off(stuck):
    stuck.config.schedule.fallback_after_minutes = 0
    sched = ArxivScheduler(stuck)
    for hour in (4, 5, 6, 7):
        assert sched.tick(datetime(2026, 11, 17, hour, 0, tzinfo=UTC)) == "not-yet"
    assert stuck.fetcher.oai_calls == []


def test_fallback_passes_the_last_days_max_id(config):
    storage = PaperStorage(config)
    papers = [
        PaperData(
            arxiv_id=i,
            title="t",
            authors=[],
            abstract="a",
            published="2026-11-16",
            categories=["cs.RO"],
            arxiv_url="",
            pdf_url="",
        )
        for i in ("2611.18562", "2611.9999", "2611.17338", "cs/0702142")
    ]
    storage.save_daily(
        DailyListing(
            date="2026-11-16",
            status={"done_at": "x"},
            papers_by_category={"cs.RO": papers},
            kinds={"cs.RO": {p.arxiv_id: "new" for p in papers}},
        )
    )
    reader = FallbackReader(
        config, storage, [date(2026, 11, 16)], oai_days=[oai_day(date(2026, 11, 17))]
    )
    sched = ArxivScheduler(reader)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    assert reader.fetcher.after_ids == ["2611.18562"]


def test_listing_recovering_to_an_earlier_oai_day_reconciles_it(config):
    """列表页卡了两天：11-17、11-18 都是 OAI 拼的，列表页先恢复到 11-17"""
    storage = PaperStorage(config)
    storage.save_daily(DailyListing(date="2026-11-16", status={"done_at": "x"}))
    reader = FallbackReader(
        config,
        storage,
        [date(2026, 11, 16)],
        oai_days=[oai_day(date(2026, 11, 17)), oai_day(date(2026, 11, 18))],
    )
    sched = ArxivScheduler(reader)
    sched.tick(datetime(2026, 11, 18, 4, 0, tzinfo=UTC))
    assert sched.tick(datetime(2026, 11, 18, 4, 30, tzinfo=UTC)) == "fallback"
    assert reader.fetched_runs == ["2026-11-17", "2026-11-18"]
    assert sched.last_done == "2026-11-18"
    reader.fetcher.dates = [date(2026, 11, 17)]
    assert sched.tick(datetime(2026, 11, 18, 5, 0, tzinfo=UTC)) == "reconciled"
    assert storage.load_daily("2026-11-17").status["source"] == "listing"
    assert sched.last_done == "2026-11-18"
    assert storage.load_state().get("last_done") != "2026-11-17"
    # 11-18 还是 OAI 拼的：继续看列表页
    assert sched.tick(datetime(2026, 11, 18, 5, 30, tzinfo=UTC)) == "not-yet"


# ---- OAI 那一版缺了尾巴：处理前先查，处理后补拉 ----


def oai_ids(reader, day):
    daily = reader.storage.load_daily(day)
    return {p.arxiv_id for p in daily.unique_papers()}


def test_oai_day_is_topped_up_while_listing_is_stuck(stuck):
    """11-18 那样：OAI 第一次只有 30 篇，后来才索引到最后 10 篇"""
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "fallback"
    assert len(oai_ids(stuck, "2026-11-17")) == 30
    stuck.fetcher.oai_days = [oai_day(date(2026, 11, 17), n=40)]
    # 补拉也按 fallback_interval_minutes（30 分钟）来
    assert sched.tick(datetime(2026, 11, 17, 4, 50, tzinfo=UTC)) == "not-yet"
    assert stuck.forced_fetched == []
    assert sched.tick(datetime(2026, 11, 17, 5, 0, tzinfo=UTC)) == "refreshed"
    assert stuck.forced_fetched == ["2026-11-17"]
    assert len(oai_ids(stuck, "2026-11-17")) == 40
    # 没有新的就不动
    assert sched.tick(datetime(2026, 11, 17, 5, 30, tzinfo=UTC)) == "not-yet"
    assert stuck.forced_fetched == ["2026-11-17"]
    # 列表页恢复以后照常用列表页重过，之后不再补拉
    stuck.fetcher.dates = [date(2026, 11, 17)]
    assert sched.tick(datetime(2026, 11, 17, 6, 0, tzinfo=UTC)) == "reconciled"
    calls = len(stuck.fetcher.oai_calls)
    assert sched.tick(datetime(2026, 11, 17, 9, 0, tzinfo=UTC)) == "waiting"
    assert len(stuck.fetcher.oai_calls) == calls


def test_top_up_never_drops_papers(stuck):
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC))
    # OAI 这次多了 5 篇、又少了前面 3 篇：宁可不动
    day = oai_day(date(2026, 11, 17), n=35)
    day.pages["cs.RO"].entries = day.pages["cs.RO"].entries[3:]
    stuck.fetcher.oai_days = [day]
    assert sched.tick(datetime(2026, 11, 17, 5, 0, tzinfo=UTC)) == "not-yet"
    assert stuck.forced_fetched == []
    assert len(oai_ids(stuck, "2026-11-17")) == 30


def test_tail_check_waits_until_oai_has_the_batch_max(stuck):
    stuck.fetcher.batch_max = "2611.20107"
    stuck.fetcher.oai_has = False
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    # 条数稳定了，但这一批最大的 2611.20107 OAI 上还没有：再等
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "not-yet"
    assert stuck.fetcher.tail_checks == ["2611.20029"]
    assert stuck.fetched_runs == []
    stuck.fetcher.oai_has = True
    assert sched.tick(datetime(2026, 11, 17, 5, 0, tzinfo=UTC)) == "fallback"
    assert stuck.fetched_runs == ["2026-11-17"]


def test_tail_check_gives_up_after_a_few_passes(stuck):
    """OAI 一直等不到尾巴：等两次以后先处理，之后靠补拉"""
    stuck.fetcher.batch_max = "2611.20107"
    stuck.fetcher.oai_has = False
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "not-yet"
    assert sched.tick(datetime(2026, 11, 17, 5, 0, tzinfo=UTC)) == "not-yet"
    assert sched.tick(datetime(2026, 11, 17, 5, 30, tzinfo=UTC)) == "fallback"
    assert stuck.fetched_runs == ["2026-11-17"]


def test_tail_check_does_not_block_when_it_cannot_tell(stuck):
    stuck.fetcher.batch_max = "2611.20107"
    stuck.fetcher.oai_has = None  # OAI 查不了
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "fallback"


def test_listing_jump_tops_up_the_oai_day_first(stuck):
    """11-17 是 OAI 拼的，列表页没回到 11-17，直接到了 11-18：先把 11-17 补全，再处理 11-18"""
    sched = ArxivScheduler(stuck)
    sched.tick(datetime(2026, 11, 17, 4, 0, tzinfo=UTC))
    assert sched.tick(datetime(2026, 11, 17, 4, 30, tzinfo=UTC)) == "fallback"
    stuck.fetcher.oai_days = [oai_day(date(2026, 11, 17), n=40)]
    stuck.fetcher.dates = [date(2026, 11, 18)]
    assert sched.tick(datetime(2026, 11, 18, 1, 0, tzinfo=UTC)) == "done"
    assert stuck.forced_fetched == ["2026-11-17"]
    assert len(oai_ids(stuck, "2026-11-17")) == 40
    assert sched.last_done == "2026-11-18"

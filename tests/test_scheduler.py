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
        self.storage.save_daily(
            DailyListing(date=day, status={"done_at": "x", "source": "oai"})
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

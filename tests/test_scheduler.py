from datetime import date, datetime, timezone

import pytest

from arxiv_reader.arxiv_fetcher import ListingNotReady
from arxiv_reader.scheduler import (
    ArxivScheduler,
    expected_announcement,
    next_listing_date,
)
from arxiv_reader.storage import DailyListing, PaperStorage

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

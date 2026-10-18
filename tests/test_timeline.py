import pandas as pd

from stocklens.models import Item
from stocklens.symbols import INDIA, US
from stocklens.timeline import attach_reactions, biggest_moves, is_unusual
from tests.conftest import make_prices


def _item(when, tz="UTC", has_time=True, title="x"):
    return Item(pd.Timestamp(when, tz=tz), title, "test", "news", has_time=has_time)


def test_news_during_market_hours_counts_same_day(prices):
    item = _item("2026-03-10 15:00", tz="America/New_York")  # Tuesday, market open
    attach_reactions([item], prices, US)
    assert str(item.reaction_day) == "2026-03-10"
    day = prices.index[prices.index.date == item.reaction_day][0]
    assert abs(item.reaction - prices["Close"].pct_change().loc[day]) < 1e-12


def test_after_close_news_counts_next_day(prices):
    item = _item("2026-03-10 21:30", tz="UTC")  # 17:30 New York
    attach_reactions([item], prices, US)
    assert str(item.reaction_day) == "2026-03-11"


def test_weekend_news_counts_monday(prices):
    item = _item("2026-03-14 10:00", tz="America/New_York")  # Saturday
    attach_reactions([item], prices, US)
    assert str(item.reaction_day) == "2026-03-16"


def test_date_only_event_is_not_shifted(prices):
    item = _item("2026-03-10", tz="America/New_York", has_time=False)
    attach_reactions([item], prices, US)
    assert str(item.reaction_day) == "2026-03-10"


def test_india_close_time():
    prices = make_prices(tz="Asia/Kolkata")
    before = _item("2026-03-10 15:00", tz="Asia/Kolkata")
    after = _item("2026-03-10 16:00", tz="Asia/Kolkata")
    attach_reactions([before, after], prices, INDIA)
    assert str(before.reaction_day) == "2026-03-10"
    assert str(after.reaction_day) == "2026-03-11"


def test_future_item_has_no_reaction(prices):
    item = _item("2030-01-01 10:00")
    attach_reactions([item], prices, US)
    assert item.reaction_day is None and item.reaction is None


def test_biggest_moves_links_causes(prices):
    prices = prices.copy()
    crash_day = prices.index[200]
    prices.loc[crash_day:, "Close"] *= 0.85  # one-day 15% drop
    cause = _item(crash_day.strftime("%Y-%m-%d") + " 10:00", tz="America/New_York", title="Fraud probe")
    unrelated = _item("2025-07-01 10:00", tz="America/New_York")
    attach_reactions([cause, unrelated], prices, US)
    moves = biggest_moves(prices, [cause, unrelated], US, n=3)
    crash = [mv for mv in moves if mv.day == crash_day.date()][0]
    assert crash.change < -0.10  # 15% cut plus that day's random noise
    assert crash.causes == [cause]
    assert is_unusual(crash.change, prices)
    assert not is_unusual(0.001, prices)

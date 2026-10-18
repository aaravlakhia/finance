"""Link news, filings and events to what the share price did."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .models import Item
from .symbols import Market


@dataclass
class Move:
    day: date
    change: float
    causes: list[Item]


def _local_day(item: Item, market: Market) -> pd.Timestamp:
    """The first calendar day an item could affect the price (after-close news counts for the next day)."""
    t = item.when.tz_convert(market.timezone)
    day = t.normalize()
    if item.has_time and t.time() >= market.close_time:
        day += pd.Timedelta(days=1)
    return day.tz_localize(None)


def attach_reactions(items: list[Item], prices: pd.DataFrame, market: Market) -> None:
    """Set reaction_day and reaction (that day's % change) on each item, in place."""
    if prices.empty:
        return
    days = prices.index.tz_localize(None).normalize() if prices.index.tz else prices.index.normalize()
    returns = prices["Close"].pct_change().to_numpy()
    for item in items:
        pos = days.searchsorted(_local_day(item, market))
        if pos >= len(days):
            continue  # hasn't happened yet / no trading since
        item.reaction_day = days[pos].date()
        r = returns[pos]
        item.reaction = None if pd.isna(r) else float(r)


def biggest_moves(prices: pd.DataFrame, items: list[Item], market: Market, n: int = 5) -> list[Move]:
    """The largest daily moves in the window, each with items that may explain it."""
    returns = prices["Close"].pct_change().dropna()
    if returns.empty:
        return []
    top = returns.abs().sort_values(ascending=False).head(n).index
    moves = []
    for ts in sorted(top):
        day = ts.date()
        causes = [i for i in items
                  if i.reaction_day == day or i.when.tz_convert(market.timezone).date() == day]
        causes.sort(key=lambda i: (not i.red_flag, i.kind != "filing", i.when))
        moves.append(Move(day, float(returns.loc[ts]), causes[:4]))
    return moves


def is_unusual(change: float | None, prices: pd.DataFrame) -> bool:
    """True when a daily move is bigger than two standard deviations."""
    if change is None:
        return False
    sd = prices["Close"].pct_change().std()
    return pd.notna(sd) and abs(change) > 2 * sd

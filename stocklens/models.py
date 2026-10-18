"""Shared data types."""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class Item:
    """One dated thing that might move a stock: a headline, a filing or an event."""

    when: pd.Timestamp              # timezone-aware
    title: str
    source: str                     # e.g. "Reuters", "SEC 8-K", "NSE", "Yahoo"
    kind: str                       # "news", "filing" or "event"
    url: str = ""
    detail: str = ""
    tags: list[str] = field(default_factory=list)
    sentiment: int = 0              # -1 negative, 0 neutral, +1 positive
    red_flag: bool = False
    has_time: bool = True           # False when only the date is known
    reaction_day: date | None = None
    reaction: float | None = None   # price change on the first trading day it could affect


@dataclass
class Signal:
    """A plain-language observation about price or fundamentals."""

    text: str
    tone: int                       # +1 bullish, -1 bearish, 0 neutral/info
    group: str = "trend"            # "trend", "momentum", "volume", "fundamentals"

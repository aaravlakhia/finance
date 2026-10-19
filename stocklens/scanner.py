"""Scan many stocks at once from a single price download."""

import logging

import numpy as np
import pandas as pd
import yfinance as yf

from .indicators import rsi, sma
from .symbols import resolve

log = logging.getLogger(__name__)


def stats(close: pd.Series) -> dict | None:
    """Trend and performance numbers for one stock's daily closes."""
    c = close.dropna()
    if len(c) < 30:
        return None
    last = float(c.iloc[-1])

    def change(n):
        return last / float(c.iloc[-1 - n]) - 1 if len(c) > n else np.nan

    s50, s200 = sma(c, 50).iloc[-1], sma(c, 200).iloc[-1]
    if pd.notna(s200) and last > s50 > s200:
        trend = "Uptrend"
    elif pd.notna(s200) and last < s50 < s200:
        trend = "Downtrend"
    else:
        trend = "Mixed"
    year = c.iloc[-252:]
    this_year = c[c.index.year == c.index[-1].year]
    before = c[c.index < this_year.index[0]]
    return {
        "Price": last, "1D": change(1), "1W": change(5), "1M": change(21), "3M": change(63),
        "1Y": change(252), "YTD": last / float(before.iloc[-1]) - 1 if len(before) else np.nan,
        "RSI": float(rsi(c).iloc[-1]), "Trend": trend,
        "From 52w high": last / float(year.max()) - 1,
        "Volatility": float(c.pct_change().iloc[-63:].std() * np.sqrt(252)),
    }


def table(closes: dict[str, pd.Series]) -> pd.DataFrame:
    rows = {}
    for symbol, series in closes.items():
        row = stats(series)
        if row:
            rows[symbol] = row
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "Symbol"
    return df


def scan(symbols: list[str], period: str = "2y") -> tuple[pd.DataFrame, list[str]]:
    """Download prices for all symbols in one request. Returns (table, symbols that failed)."""
    yahoo = list(dict.fromkeys(resolve(s).yahoo for s in symbols))
    data = yf.download(yahoo, period=period, group_by="ticker", auto_adjust=True, progress=False, threads=True)
    closes = {}
    if data is not None and not data.empty:
        top = data.columns.get_level_values(0) if isinstance(data.columns, pd.MultiIndex) else []
        for sym in yahoo:
            if sym in top and "Close" in data[sym]:
                closes[sym] = data[sym]["Close"]
    result = table(closes)
    return result, [s for s in yahoo if s not in result.index]

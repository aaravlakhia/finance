"""Turn indicator values into plain-language signals."""

import numpy as np
import pandas as pd

from .models import Signal

PERFORMANCE_WINDOWS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def performance(df: pd.DataFrame) -> dict[str, float]:
    """Price change over standard look-back windows (trading days)."""
    close = df["Close"].dropna()
    out = {}
    for label, n in PERFORMANCE_WINDOWS.items():
        out[label] = close.iloc[-1] / close.iloc[-1 - n] - 1 if len(close) > n else np.nan
    this_year = close[close.index.year == close.index[-1].year]
    prior = close[close.index < this_year.index[0]]
    out["YTD"] = close.iloc[-1] / prior.iloc[-1] - 1 if len(prior) else np.nan
    return out


def risk_stats(df: pd.DataFrame) -> dict[str, float]:
    close = df["Close"].dropna()
    year = close.iloc[-252:]
    returns = close.pct_change().dropna()
    drawdown = year / year.cummax() - 1
    return {
        "high_52w": year.max(),
        "low_52w": year.min(),
        "volatility": returns.iloc[-63:].std() * np.sqrt(252),
        "max_drawdown": drawdown.min(),
    }


def _crossed(a: pd.Series, b: pd.Series, lookback: int) -> tuple[str | None, int | None]:
    """Did series a cross b within the last `lookback` rows? Returns (direction, days_ago)."""
    above = (a > b).where(a.notna() & b.notna())
    recent = above.iloc[-(lookback + 1):].dropna()
    for i in range(len(recent) - 1, 0, -1):
        if recent.iloc[i] != recent.iloc[i - 1]:
            return ("up" if recent.iloc[i] else "down"), len(recent) - 1 - i
    return None, None


def price_signals(df: pd.DataFrame) -> list[Signal]:
    last = df.iloc[-1]
    close = last["Close"]
    out: list[Signal] = []

    s50, s200 = last.get("SMA50"), last.get("SMA200")
    if pd.notna(s50) and pd.notna(s200):
        if close > s50 > s200:
            out.append(Signal("Uptrend: price is above its 50-day and 200-day averages", +1))
        elif close < s50 < s200:
            out.append(Signal("Downtrend: price is below its 50-day and 200-day averages", -1))
        elif close > s200:
            out.append(Signal("Above the 200-day average (long-term trend up) but momentum is mixed", 0))
        else:
            out.append(Signal("Below the 200-day average (long-term trend down) but momentum is mixed", 0))
        direction, ago = _crossed(df["SMA50"], df["SMA200"], 30)
        if direction == "up":
            out.append(Signal(f"Golden cross {ago} trading days ago (50-day average moved above 200-day)", +1))
        elif direction == "down":
            out.append(Signal(f"Death cross {ago} trading days ago (50-day average moved below 200-day)", -1))
    elif pd.notna(s50):
        tone = 1 if close > s50 else -1
        side = "above" if tone > 0 else "below"
        out.append(Signal(f"Price is {side} its 50-day average (not enough history for 200-day)", tone))

    r = last.get("RSI14")
    if pd.notna(r):
        if r >= 70:
            out.append(Signal(f"RSI {r:.0f}: overbought - the rise may be stretched", -1, "momentum"))
        elif r <= 30:
            out.append(Signal(f"RSI {r:.0f}: oversold - the fall may be stretched", +1, "momentum"))
        else:
            out.append(Signal(f"RSI {r:.0f}: neutral", 0, "momentum"))

    if "MACD" in df:
        direction, ago = _crossed(df["MACD"], df["MACD_signal"], 5)
        if direction == "up":
            out.append(Signal(f"MACD crossed above its signal line {ago} days ago (momentum turning up)", +1, "momentum"))
        elif direction == "down":
            out.append(Signal(f"MACD crossed below its signal line {ago} days ago (momentum turning down)", -1, "momentum"))

    upper, lower = last.get("BB_upper"), last.get("BB_lower")
    if pd.notna(upper) and close > upper:
        out.append(Signal("Closed above the upper Bollinger band (unusually strong move)", 0, "momentum"))
    elif pd.notna(lower) and close < lower:
        out.append(Signal("Closed below the lower Bollinger band (unusually weak move)", 0, "momentum"))

    year = df["Close"].iloc[-252:]
    if close >= year.max() * 0.97:
        out.append(Signal("Trading near its 52-week high", +1))
    elif close <= year.min() * 1.03:
        out.append(Signal("Trading near its 52-week low", -1))

    avg_vol = last.get("Vol_avg20")
    if pd.notna(avg_vol) and avg_vol > 0 and last["Volume"] > 2 * avg_vol:
        ret = last.get("Return", 0) or 0
        move = "up" if ret >= 0 else "down"
        out.append(Signal(f"Heavy volume today ({last['Volume'] / avg_vol:.1f}x the 20-day average) on a {move} day",
                          1 if ret >= 0 else -1, "volume"))
    return out


def fundamental_signals(statement: pd.DataFrame, label: str) -> list[Signal]:
    """Signals from a summarised income statement (oldest -> newest rows)."""
    out: list[Signal] = []
    if statement is None or statement.empty:
        return out

    rev = statement.get("Revenue", pd.Series(dtype=float)).dropna()
    if len(rev) >= 3:
        growth = rev.pct_change().dropna()
        if (growth > 0).all():
            out.append(Signal(f"Revenue grew in each of the last {len(growth)} {label} periods", +1, "fundamentals"))
        elif (growth.iloc[-2:] < 0).all():
            out.append(Signal(f"Revenue fell in the last two {label} periods", -1, "fundamentals"))

    profit = statement.get("Net profit", pd.Series(dtype=float)).dropna()
    if len(profit):
        if profit.iloc[-1] < 0:
            out.append(Signal(f"Made a net loss in the latest {label} period", -1, "fundamentals"))
        elif len(profit) >= 2 and profit.iloc[-2] > 0:
            change = profit.iloc[-1] / profit.iloc[-2] - 1
            if change > 0.10:
                out.append(Signal(f"Net profit up {change:.0%} vs the previous {label} period", +1, "fundamentals"))
            elif change < -0.10:
                out.append(Signal(f"Net profit down {abs(change):.0%} vs the previous {label} period", -1, "fundamentals"))

    margin = statement.get("Net margin", pd.Series(dtype=float)).dropna()
    if len(margin) >= 2:
        diff = margin.iloc[-1] - margin.iloc[-2]
        if abs(diff) >= 0.02:
            word = "widened" if diff > 0 else "narrowed"
            out.append(Signal(f"Net margin {word} to {margin.iloc[-1]:.1%} ({diff * 100:+.1f} pts)",
                              1 if diff > 0 else -1, "fundamentals"))
    return out


def overall(signals: list[Signal]) -> tuple[int, str]:
    score = sum(s.tone for s in signals)
    if score >= 2:
        return score, "Bullish leaning"
    if score <= -2:
        return score, "Bearish leaning"
    return score, "Neutral / mixed"

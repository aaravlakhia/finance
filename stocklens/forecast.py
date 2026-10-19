"""Probabilities, not prophecies.

Nobody can predict an exact future price. What we *can* measure from a stock's
own history is (a) how far it usually moves, (b) what happened after past days
that looked like today, (c) how often that kind of reasoning would have been
right before, and (d) whether a simple trend rule beat buy-and-hold.
"""

import numpy as np
import pandas as pd

HORIZONS = {"1 month": 21, "3 months": 63, "6 months": 126}
RSI_BINS = [0, 35, 50, 65, 100]
RSI_WORDS = ["weak momentum (RSI under 35)", "soft momentum (RSI 35-50)",
             "firm momentum (RSI 50-65)", "strong momentum (RSI over 65)"]


# --------------------------------------------------------------- ranges --

def simulate(close: pd.Series, days: int, n_paths: int = 2000, lookback: int = 504,
             seed: int = 7) -> np.ndarray:
    """Future price paths built by replaying randomly chosen past daily moves.

    The moves are re-centred on zero, so the paths carry the stock's real
    volatility (including its big days) but no assumed trend. Returns an array
    of shape (n_paths, days).
    """
    r = np.log(close).diff().dropna().iloc[-lookback:].to_numpy()
    if len(r) < 60:
        return np.empty((0, days))
    r = r - r.mean()
    picks = np.random.default_rng(seed).choice(r, size=(n_paths, days), replace=True)
    return float(close.iloc[-1]) * np.exp(np.cumsum(picks, axis=1))


def cone(close: pd.Series, days: int = 63) -> pd.DataFrame:
    """Percentile bands (5/25/50/75/95) for each future trading day."""
    paths = simulate(close, days)
    if paths.size == 0:
        return pd.DataFrame()
    idx = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=days, tz=close.index.tz)
    q = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    return pd.DataFrame(q.T, index=idx, columns=["p05", "p25", "p50", "p75", "p95"])


def ranges(close: pd.Series) -> pd.DataFrame:
    """Likely price ranges at 1, 3 and 6 months."""
    paths = simulate(close, max(HORIZONS.values()))
    if paths.size == 0:
        return pd.DataFrame()
    rows = {}
    for label, d in HORIZONS.items():
        end = paths[:, d - 1]
        p05, p25, p75, p95 = np.percentile(end, [5, 25, 75, 95])
        rows[label] = {"low90": p05, "low50": p25, "high50": p75, "high90": p95,
                       "typical_move": (p75 - p25) / 2 / float(close.iloc[-1])}
    return pd.DataFrame(rows).T


# ------------------------------------------------------------- analogs --

def _setup(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per-day setup: trend (1 above / 0 below 200-day avg, -1 unknown) and RSI bucket (-1 unknown)."""
    trend = np.where(df["SMA200"].isna(), -1, (df["Close"] > df["SMA200"]).astype(int))
    bucket = pd.cut(df["RSI14"], RSI_BINS, labels=False, include_lowest=True)
    return trend, bucket.fillna(-1).astype(int).to_numpy()


def describe_setup(trend: int, bucket: int) -> str:
    side = "above" if trend == 1 else "below"
    return f"price {side} its 200-day average with {RSI_WORDS[bucket]}"


def analogs(df: pd.DataFrame, horizons=(21, 63)) -> dict | None:
    """What happened after past days with the same setup as today."""
    trend, bucket = _setup(df)
    t, b = trend[-1], bucket[-1]
    if t < 0 or b < 0:
        return None
    close = df["Close"].to_numpy()
    same = (trend == t) & (bucket == b)
    rows = []
    for h in horizons:
        fwd = np.full(len(close), np.nan)
        fwd[:-h] = close[h:] / close[:-h] - 1
        known = ~np.isnan(fwd)
        hits = fwd[same & known]
        everyone = fwd[known]
        if len(hits) < 15:
            continue
        rows.append({
            "horizon": "1 month" if h == 21 else "3 months" if h == 63 else f"{h} days",
            "days": h, "matches": len(hits),
            "pct_higher": float((hits > 0).mean()), "median": float(np.median(hits)),
            "p25": float(np.percentile(hits, 25)), "p75": float(np.percentile(hits, 75)),
            "pct_higher_all": float((everyone > 0).mean()), "median_all": float(np.median(everyone)),
        })
    if not rows:
        return None
    return {"setup": describe_setup(t, b), "rows": rows}


def track_record(df: pd.DataFrame, h: int = 21, step: int = 5, warmup: int = 250) -> dict | None:
    """Walk forward through history and score the analog method honestly.

    At each test day it may only use outcomes that were already known then.
    It "predicts up" when most matching past days went up, and we compare that
    with simply always guessing "up".
    """
    trend, bucket = _setup(df)
    close = df["Close"].to_numpy()
    n = len(close)
    fwd = np.full(n, np.nan)
    fwd[:-h] = close[h:] / close[:-h] - 1
    calls, actual = [], []
    for i in range(warmup, n - h, step):
        if trend[i] < 0 or bucket[i] < 0:
            continue
        known = slice(0, i - h)  # outcomes fully known by day i
        same = (trend[known] == trend[i]) & (bucket[known] == bucket[i])
        past = fwd[known][same]
        if len(past) < 20:
            continue
        calls.append((past > 0).mean() > 0.5)
        actual.append(fwd[i] > 0)
    if len(calls) < 20:
        return None
    calls, actual = np.array(calls), np.array(actual)
    return {"tests": len(calls), "accuracy": float((calls == actual).mean()),
            "always_up": float(actual.mean())}


# ------------------------------------------------------------ backtest --

def trend_backtest(df: pd.DataFrame) -> dict | None:
    """Compare buy-and-hold with "own it only while price is above its 200-day average".

    Trades happen the day after the signal; costs and taxes are ignored.
    """
    d = df.dropna(subset=["SMA200"])
    if len(d) < 120:
        return None
    ret = d["Close"].pct_change().fillna(0)
    invested = (d["Close"] > d["SMA200"]).astype(float).shift(1).fillna(0)
    equity = pd.DataFrame({"Buy and hold": (1 + ret).cumprod(),
                           "Trend rule": (1 + invested * ret).cumprod()})
    years = (d.index[-1] - d.index[0]).days / 365.25

    def stats(curve: pd.Series) -> dict:
        return {"total": float(curve.iloc[-1] - 1),
                "cagr": float(curve.iloc[-1] ** (1 / years) - 1) if years > 0 else np.nan,
                "max_drawdown": float((curve / curve.cummax() - 1).min())}

    return {"equity": equity, "years": years, "hold": stats(equity["Buy and hold"]),
            "rule": stats(equity["Trend rule"]), "time_invested": float(invested.mean()),
            "switches": int(invested.diff().abs().sum())}

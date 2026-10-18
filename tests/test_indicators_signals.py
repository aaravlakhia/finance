import numpy as np
import pandas as pd

from stocklens import indicators, signals
from tests.conftest import make_prices


def test_sma_and_rsi_bounds(prices):
    df = indicators.add_all(prices)
    assert df["SMA20"].iloc[:19].isna().all()
    assert np.isclose(df["SMA20"].iloc[19], prices["Close"].iloc[:20].mean())
    rsi = df["RSI14"].dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert indicators.rsi(up).iloc[-1] == 100
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert indicators.rsi(down).iloc[-1] < 1


def test_macd_columns(prices):
    out = indicators.macd(prices["Close"])
    assert list(out.columns) == ["MACD", "MACD_signal", "MACD_hist"]
    assert np.allclose((out["MACD"] - out["MACD_signal"]).dropna(), out["MACD_hist"].dropna())


def test_uptrend_detected():
    df = indicators.add_all(make_prices(drift=0.004))
    texts = " ".join(s.text for s in signals.price_signals(df))
    assert "Uptrend" in texts
    score, verdict = signals.overall(signals.price_signals(df))
    assert score > 0


def test_downtrend_detected():
    df = indicators.add_all(make_prices(drift=-0.004))
    texts = " ".join(s.text for s in signals.price_signals(df))
    assert "Downtrend" in texts


def test_golden_cross_found():
    # Falls for 250 days, then rallies hard: the 50-day average overtakes the 200-day.
    close = np.concatenate([np.linspace(200, 100, 250), np.linspace(100, 190, 60)])
    idx = pd.bdate_range("2024-01-01", periods=len(close), tz="America/New_York")
    df = pd.DataFrame({"Close": close, "Volume": 1e6}, index=idx)
    df = indicators.add_all(df)
    cross_day = ((df["SMA50"] > df["SMA200"]) & (df["SMA50"].shift() <= df["SMA200"].shift())).idxmax()
    df = df.loc[:cross_day + pd.Timedelta(days=7)]
    assert any("Golden cross" in s.text for s in signals.price_signals(df))


def test_performance_windows(prices):
    perf = signals.performance(prices)
    close = prices["Close"]
    assert np.isclose(perf["1D"], close.iloc[-1] / close.iloc[-2] - 1)
    assert np.isclose(perf["1M"], close.iloc[-1] / close.iloc[-22] - 1)
    assert set(perf) == {"1D", "1W", "1M", "3M", "6M", "1Y", "YTD"}


def test_fundamental_signals():
    idx = pd.to_datetime(["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"])
    st = pd.DataFrame({"Revenue": [100.0, 110, 120, 130], "Net profit": [10.0, 11, 12, 15]}, index=idx)
    st["Net margin"] = st["Net profit"] / st["Revenue"]
    texts = [s.text for s in signals.fundamental_signals(st, "quarterly")]
    assert any("Revenue grew in each of the last 3" in t for t in texts)
    assert any("Net profit up 25%" in t for t in texts)

    loss = st.copy()
    loss.loc[loss.index[-1], "Net profit"] = -5
    assert any("net loss" in s.text for s in signals.fundamental_signals(loss, "quarterly"))

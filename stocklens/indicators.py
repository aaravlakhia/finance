"""Technical indicators computed with plain pandas (no extra libraries)."""

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder's smoothing (0-100)."""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    # No losses at all in the window means RSI is 100.
    return out.where(loss != 0, 100.0).where(gain.notna())


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(series, fast) - ema(series, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"MACD": line, "MACD_signal": sig, "MACD_hist": line - sig})


def bollinger(series: pd.Series, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(series, window)
    sd = series.rolling(window, min_periods=window).std()
    return pd.DataFrame({"BB_mid": mid, "BB_upper": mid + k * sd, "BB_lower": mid - k * sd})


def add_all(prices: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of an OHLCV frame with indicator columns added."""
    df = prices.copy()
    close = df["Close"]
    df["SMA20"] = sma(close, 20)
    df["SMA50"] = sma(close, 50)
    df["SMA200"] = sma(close, 200)
    df["RSI14"] = rsi(close, 14)
    df = df.join(macd(close)).join(bollinger(close))
    df["Vol_avg20"] = sma(df["Volume"], 20)
    df["Return"] = close.pct_change()
    return df

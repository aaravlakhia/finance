import numpy as np
import pandas as pd
import pytest


def make_prices(days=320, tz="America/New_York", seed=1, drift=0.001, start="2025-06-02"):
    """Synthetic OHLCV history shaped like yfinance output."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days, tz=tz, name="Date")
    returns = rng.normal(drift, 0.012, days)
    close = 100 * np.exp(np.cumsum(returns))
    df = pd.DataFrame({
        "Open": close * 0.998, "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": rng.integers(1_000_000, 2_000_000, days).astype(float),
        "Dividends": 0.0, "Stock Splits": 0.0,
    }, index=idx)
    return df


@pytest.fixture
def prices():
    return make_prices()

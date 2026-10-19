"""'What if I had invested?' calculators. Prices are dividend-adjusted, so
dividends count as reinvested. Taxes and brokerage are ignored."""

import numpy as np
import pandas as pd


def _since(close: pd.Series, years: float) -> pd.Series:
    start = close.index[-1] - pd.DateOffset(days=round(years * 365.25))
    return close[close.index >= start]


def lump_sum(close: pd.Series, amount: float, years: float) -> dict | None:
    window = _since(close.dropna(), years)
    if len(window) < 2:
        return None
    start_price, end_price = float(window.iloc[0]), float(window.iloc[-1])
    value = amount * end_price / start_price
    span = (window.index[-1] - window.index[0]).days / 365.25
    return {"start": window.index[0].date(), "invested": amount, "value": value,
            "gain": value - amount, "total_return": value / amount - 1,
            "cagr": (value / amount) ** (1 / span) - 1 if span > 0 else np.nan}


def xirr(cashflows: list[tuple[pd.Timestamp, float]]) -> float:
    """Annualised return of dated cash flows (negative = money in), found by bisection."""
    t0 = cashflows[0][0]
    times = np.array([(d - t0) / pd.Timedelta(days=365.25) for d, _ in cashflows])
    amounts = np.array([a for _, a in cashflows])

    def npv(rate):
        return float((amounts / (1 + rate) ** times).sum())

    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return np.nan
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def sip(close: pd.Series, monthly: float, years: float) -> dict | None:
    """Invest a fixed amount on the first trading day of every month."""
    window = _since(close.dropna(), years)
    if len(window) < 30:
        return None
    days = window.index.tz_localize(None) if window.index.tz is not None else window.index
    month = days.to_period("M")
    buys = window[~month.duplicated()]
    units = (monthly / buys).cumsum()
    invested = pd.Series(monthly, index=buys.index).cumsum()
    path = pd.DataFrame({"Invested": invested, "Units": units}).reindex(window.index).ffill()
    path["Value"] = path["Units"] * window
    value = float(path["Value"].iloc[-1])
    total_in = float(invested.iloc[-1])
    flows = [(d, -monthly) for d in buys.index] + [(window.index[-1], value)]
    return {"start": buys.index[0].date(), "instalments": len(buys), "invested": total_in,
            "value": value, "gain": value - total_in, "total_return": value / total_in - 1,
            "xirr": xirr(flows), "path": path[["Invested", "Value"]]}

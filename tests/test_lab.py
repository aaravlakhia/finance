"""Prediction lab, calculators, market comparison and the checklist (offline)."""

import numpy as np
import pandas as pd
import pytest

from stocklens import forecast, indicators, invest, scorecard, signals
from tests.conftest import make_prices


def _series(values, start="2021-01-04", tz="Asia/Kolkata"):
    idx = pd.bdate_range(start, periods=len(values), tz=tz)
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def _frame(close: pd.Series) -> pd.DataFrame:
    return indicators.add_all(pd.DataFrame({"Close": close, "Volume": 1e6}))


# ------------------------------------------------------------- ranges --

def test_simulation_has_no_built_in_trend():
    close = make_prices(days=600, drift=0.004)["Close"]  # strong past uptrend
    end = forecast.simulate(close, 63)[:, -1]
    assert abs(np.median(end) / close.iloc[-1] - 1) < 0.03
    assert np.array_equal(forecast.simulate(close, 10), forecast.simulate(close, 10))  # reproducible


def test_cone_and_ranges_are_ordered_and_widen():
    close = make_prices(days=600)["Close"]
    c = forecast.cone(close, 63)
    assert c.index[0] > close.index[-1] and len(c) == 63
    assert (c["p05"] < c["p25"]).all() and (c["p25"] < c["p75"]).all() and (c["p75"] < c["p95"]).all()
    r = forecast.ranges(close)
    widths = (r["high90"] - r["low90"]).to_numpy()
    assert list(r.index) == ["1 month", "3 months", "6 months"]
    assert widths[0] < widths[1] < widths[2]
    assert forecast.cone(close.iloc[:30]).empty  # too little history


# ------------------------------------------------- analogs & track record --

def test_analogs_on_steady_climb():
    rng = np.random.default_rng(3)
    close = _series(100 * np.exp(np.cumsum(0.002 + rng.normal(0, 0.004, 900))))
    a = forecast.analogs(_frame(close))
    assert a and "above its 200-day average" in a["setup"]
    one = a["rows"][0]
    assert one["horizon"] == "1 month" and one["matches"] >= 15
    assert one["pct_higher"] > 0.9


def test_track_record_perfect_when_market_only_rises():
    rng = np.random.default_rng(4)
    close = _series(100 * np.exp(np.cumsum(0.003 + rng.normal(0, 0.003, 900))))
    t = forecast.track_record(_frame(close))
    assert t["tests"] >= 20
    assert t["always_up"] == 1.0 and t["accuracy"] == 1.0


def test_track_record_uses_only_past_outcomes():
    rng = np.random.default_rng(5)
    base = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 900)))
    df = _frame(_series(base))
    before = forecast.track_record(df.iloc[:700])
    # Rewriting prices after day 700 must not change any call made on earlier days.
    changed = base.copy()
    changed[700:] *= 3
    after = forecast.track_record(_frame(_series(changed)).iloc[:700])
    assert before == after


# ------------------------------------------------------------ backtest --

def test_trend_rule_sidesteps_a_crash():
    up = np.linspace(100, 200, 400)
    down = np.linspace(200, 80, 200)
    df = _frame(_series(np.concatenate([up, down])))
    b = forecast.trend_backtest(df)
    assert b["rule"]["max_drawdown"] > b["hold"]["max_drawdown"]  # smaller loss
    assert 0 < b["time_invested"] < 1 and b["switches"] >= 1
    assert list(b["equity"].columns) == ["Buy and hold", "Trend rule"]


# --------------------------------------------------------- calculators --

def test_lump_sum_cagr():
    days = pd.bdate_range("2020-01-01", "2025-01-01", tz="America/New_York")
    years = (days - days[0]).days / 365.25
    close = pd.Series(100 * 1.10 ** years, index=days)
    out = invest.lump_sum(close, 1000, 3)
    assert out["cagr"] == pytest.approx(0.10, abs=0.002)
    assert out["value"] == pytest.approx(1000 * 1.10 ** 3, rel=0.01)


def test_sip_flat_price_and_xirr():
    close = pd.Series(50.0, index=pd.bdate_range("2023-01-02", "2025-12-31", tz="Asia/Kolkata"))
    out = invest.sip(close, 5000, 2)
    assert out["value"] == pytest.approx(out["invested"])
    assert out["xirr"] == pytest.approx(0.0, abs=1e-6)
    assert out["instalments"] in (24, 25)
    t0 = pd.Timestamp("2024-01-01")
    assert invest.xirr([(t0, -100), (t0 + pd.Timedelta(days=365.25), 110)]) == pytest.approx(0.10, abs=1e-6)


# ------------------------------------------------------ market context --

def test_relative_beta_and_gap():
    rng = np.random.default_rng(6)
    idx_ret = rng.normal(0.0004, 0.01, 400)
    index = _series(100 * np.cumprod(1 + idx_ret), tz="America/New_York")
    stock = _series(100 * np.cumprod(1 + 2 * idx_ret), tz="America/New_York")
    rel = signals.relative(stock, index)
    assert rel["beta"] == pytest.approx(2.0, rel=1e-6)
    assert rel["gap"] == pytest.approx(rel["stock"] - rel["index"])
    assert signals.relative(stock, pd.Series(dtype=float)) is None


# ------------------------------------------------------------ checklist --

class _R:
    """Just the report fields the checklist reads."""

    def __init__(self, profile, timeline=()):
        self.history = indicators.add_all(make_prices(days=400, drift=0.003))
        self.profile = profile
        self.performance = signals.performance(self.history)
        self.risk = signals.risk_stats(self.history)
        self.quarterly = self.annual = pd.DataFrame()
        self.timeline = list(timeline)
        self.last_close = float(self.history["Close"].iloc[-1])


def test_checklist_scores_and_reasons():
    r = _R({"revenueGrowth": 0.25, "earningsGrowth": 0.3, "profitMargins": 0.25, "returnOnEquity": 0.3,
            "trailingPE": 14, "forwardPE": 12, "debtToEquity": 20, "currentRatio": 2, "freeCashflow": 1e9,
            "targetMeanPrice": 1e9})
    pillars = scorecard.evaluate(r)
    assert [p.name for p in pillars] == ["Trend", "Growth", "Profitability", "Valuation",
                                         "Financial health", "News & risk"]
    assert all(0 <= p.score <= 10 for p in pillars)
    assert all(p.reasons for p in pillars)
    score, label = scorecard.overall(pillars)
    assert score >= 7 and label == "Strong"


def test_checklist_handles_missing_data_and_banks():
    pillars = {p.name: p for p in scorecard.evaluate(_R({"sector": "Financial Services", "debtToEquity": 900}))}
    assert pillars["Growth"].score is None and pillars["Valuation"].score is None
    assert pillars["Financial health"].score is None
    assert "banks" in pillars["Financial health"].reasons[0]
    loss = scorecard.valuation(_R({"trailingPE": -5}))
    assert loss.score == 2 and "isn't meaningful" in loss.reasons[0]

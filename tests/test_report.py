"""End-to-end report build with yfinance and the web sources replaced by fakes."""

from datetime import date

import pandas as pd
import pytest

from stocklens import cli, filings, news, report
from stocklens.models import Item
from tests.conftest import make_prices


class FakeTicker:
    def __init__(self, symbol, tz):
        self.symbol = symbol
        self._prices = make_prices(days=520, tz=tz, start="2024-09-02")
        self._prices.iloc[-60, self._prices.columns.get_loc("Dividends")] = 4.5
        self.info = {"longName": "Acme Industries Limited", "sector": "Technology",
                     "industry": "IT Services", "marketCap": 6.3e12, "trailingPE": 24.1, "forwardPE": 21.0,
                     "profitMargins": 0.17, "returnOnEquity": 0.3, "revenueGrowth": 0.08, "debtToEquity": 20.0,
                     "targetLowPrice": 120.0, "targetMeanPrice": 150.0, "targetHighPrice": 180.0,
                     "recommendationKey": "buy", "numberOfAnalystOpinions": 30}
        cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"])
        self.quarterly_income_stmt = pd.DataFrame(
            [[4.2e11, 4.0e11, 3.9e11, 3.8e11], [7.1e10, 6.5e10, 6.4e10, 6.0e10], [17.1, 15.7, 15.4, 14.5]],
            index=["Total Revenue", "Net Income", "Diluted EPS"], columns=cols)
        self.income_stmt = self.quarterly_income_stmt * 4
        self.calendar = {"Earnings Date": [date(2030, 1, 15)], "Earnings Average": 18.2,
                         "Ex-Dividend Date": date(2030, 2, 1)}
        self.news = [{"content": {"title": "Acme shares jump after strong quarter",
                                  "pubDate": self._prices.index[-5].strftime("%Y-%m-%dT05:00:00Z"),
                                  "provider": {"displayName": "Yahoo Finance"}}}]

    def history(self, period, auto_adjust=True):
        return self._prices

    def get_earnings_dates(self, limit=12):
        raise RuntimeError("scrape failed")  # exercise the warning path


@pytest.fixture
def fake_sources(monkeypatch):
    def fake_news(name, ticker, limit):
        assert name == "Acme Industries"
        when = pd.Timestamp("2026-07-01 10:00", tz=ticker.market.timezone)
        return [Item(when, "Regulator opens probe into Acme accounting", "Wire", "news",
                     tags=["scandal/legal"], sentiment=-1, red_flag=True)], []

    monkeypatch.setattr(news, "fetch", fake_news)
    monkeypatch.setattr(filings, "fetch", lambda ticker, since: ([], ["NSE filings unavailable (Timeout)"]))
    monkeypatch.setattr(report.yf, "Ticker",
                        lambda s: FakeTicker(s, "Asia/Kolkata" if s.endswith((".NS", ".BO")) else "America/New_York"))


def test_build_india_report(fake_sources):
    r = report.build("ACME", market="in", period="6mo")
    assert r.ticker.yahoo == "ACME.NS"
    assert r.name == "Acme Industries Limited"
    assert len(r.prices) < len(r.history)
    assert r.prices.index[0] >= r.history.index[-1] - pd.DateOffset(months=6)
    assert len(r.red_flags) == 1 and r.red_flags[0].reaction_day is not None
    assert [e.title for e in r.upcoming] == ["Earnings announcement", "Ex-dividend date"]
    assert any(i.title.startswith("Ex-dividend (4.50") for i in r.timeline)
    assert any("Earnings history unavailable" in w for w in r.warnings)
    assert r.dividend_yield and r.dividend_yield > 0
    assert len(r.moves) == 5

    # prediction lab, market context, checklist and briefing
    assert list(r.ranges.index) == ["1 month", "3 months", "6 months"] and len(r.cone) == 63
    assert r.analogs and r.backtest and r.relative and r.relative["beta"] == pytest.approx(1.0)
    assert len(r.pillars) == 6 and 0 <= r.checklist_score <= 10 and r.checklist_label
    brief = " ".join(r.briefing)
    for phrase in ("Acme Industries Limited is at ₹", "NIFTY 50", "1 red flag", "likely (50%)",
                   "Investment checklist"):
        assert phrase in brief

    text = cli.format_report(r)
    for heading in ("BRIEFING", "INVESTMENT CHECKLIST", "OUTLOOK", "TREND", "FINANCIALS", "COMING UP",
                    "RED FLAGS (1)", "BIGGEST MOVES", "TIMELINE"):
        assert heading in text
    assert "₹6.30 lakh Cr" in text
    assert "Regulator opens probe" in text


def test_watchlist_and_cli_exit_codes(fake_sources, capsys, monkeypatch):
    assert cli.main(["AAPL", "INFY.NS"]) == 0
    out = capsys.readouterr().out
    assert "AAPL" in out and "INFY.NS" in out and "Trend" in out

    def no_data(*a, **k):
        raise report.NoPriceData("No price data for ZZZZ")

    monkeypatch.setattr(cli, "build", no_data)
    assert cli.main(["ZZZZ"]) == 1


def test_connection_error_message(fake_sources, monkeypatch):
    def offline(self, period, auto_adjust=True):
        raise ConnectionError("no internet")

    monkeypatch.setattr(FakeTicker, "history", offline)
    with pytest.raises(report.NoPriceData, match="internet connection"):
        report.build("AAPL")


def test_bad_period():
    with pytest.raises(ValueError):
        report.build("AAPL", period="10y")


def test_charts_build(fake_sources):
    charts = pytest.importorskip("stocklens.charts")
    r = report.build("AAPL", period="1y")
    m = r.ticker.market
    for mode in ("light", "dark"):
        fig = charts.price_chart(r.prices, r.timeline, m, mode, show_bands=True, show_macd=True, cone=r.cone)
        names = {t.name for t in fig.data}
        assert {"Red flag", "Likely range (50%)", "Very likely range (90%)"} <= names
        charts.financials_chart(r.quarterly, m, mode)
        assert charts.vs_market_chart(r.prices["Close"], r.benchmark, "AAPL", m.benchmark_name, mode)
        charts.lines_chart(r.backtest["equity"] * 100, ["#000", "#111"], mode)
        charts.target_chart(r.last_close, 120, 150, 180, m, mode)

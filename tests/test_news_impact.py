"""News impact, the market scanner and stock search (offline)."""

import numpy as np
import pandas as pd
import pytest

from stocklens import impact, scanner, search
from stocklens.classify import RED_FLAG
from stocklens.models import Item
from tests.conftest import make_prices


def _item(title, tags, when="2026-03-10 15:00", sentiment=0, red=False, kind="news", reaction=None, day=None):
    it = Item(pd.Timestamp(when, tz="America/New_York"), title, "Wire", kind, tags=tags,
              sentiment=sentiment, red_flag=red)
    it.reaction, it.reaction_day = reaction, day
    return it


# ---------------------------------------------------------------- impact --

def test_topic_priority_and_meaning():
    both = _item("Board meeting to approve Q2 results", ["earnings", "meeting"])
    assert impact.topic_of(both) == "meeting"
    assert impact.topic_of(_item("Q2 profit rises", ["earnings", "deal"])) == "earnings"
    probe = _item("Probe into results", ["earnings", RED_FLAG], red=True, sentiment=-1)
    assert impact.topic_of(probe) == RED_FLAG
    assert impact.topic_of(_item("Company opens office", [])) == "other"
    good = _item("Profit beats estimates", ["earnings"], sentiment=1)
    assert "Good results usually lift" in impact.meaning(good)
    assert "uncertainty" in impact.meaning(probe)
    assert impact.meaning(_item("AGM on Friday", ["meeting"], sentiment=1))  # falls back to neutral text


def test_history_counts_each_day_once():
    prices = make_prices()
    d1, d2 = pd.Timestamp("2026-01-05").date(), pd.Timestamp("2026-02-05").date()
    items = [
        _item("Q3 beat", ["earnings"], reaction=0.05, day=d1),
        _item("Q3 beat, more coverage", ["earnings"], reaction=0.05, day=d1),
        _item("Q4 miss", ["earnings"], reaction=-0.03, day=d2),
        _item("No reaction yet", ["earnings"]),
    ]
    s = impact.history(items, prices)["earnings"]
    assert s.days == 2
    assert s.avg_move == pytest.approx(0.01)
    assert s.avg_size == pytest.approx(0.04)
    assert s.up_share == pytest.approx(0.5)
    assert s.vs_normal == pytest.approx(0.04 / impact.typical_move(prices))


def test_rating_uses_history_when_enough():
    stats = {"earnings": impact.TopicStats("earnings", 5, 0.01, 0.05, 0.6, 2.5),
             "deal": impact.TopicStats("deal", 2, 0.0, 0.05, 0.5, 4.0)}
    assert impact.rating(_item("Beat", ["earnings"], sentiment=1), stats) == ("Positive", "High")
    assert impact.rating(_item("Deal", ["deal"]), stats) == ("Unclear", "Medium")  # too few days: default
    assert impact.rating(_item("Fraud", [RED_FLAG], red=True), {}) == ("Negative", "High")


def test_grouped_order_and_pulse():
    items = [
        _item("Old result", ["earnings"], when="2026-03-01 10:00"),
        _item("New result", ["earnings"], when="2026-03-09 10:00", sentiment=1),
        _item("Probe", [RED_FLAG], red=True, sentiment=-1),
        _item("Dividend paid", ["dividend/buyback"], kind="event"),
    ]
    g = impact.grouped(items)
    assert list(g) == [RED_FLAG, "earnings"]  # events excluded, red flags first
    assert [i.title for i in g["earnings"]] == ["New result", "Old result"]

    now = pd.Timestamp("2026-03-12", tz="UTC")
    p = impact.pulse(items, weeks=4, now=now)
    assert list(p.columns) == ["Positive", "Neutral", "Negative"]
    assert p.to_numpy().sum() == 3 and p["Negative"].sum() == 1 and p["Positive"].sum() == 1
    assert impact.pulse([], weeks=4, now=now).to_numpy().sum() == 0


# --------------------------------------------------------------- scanner --

def test_scanner_stats_and_table():
    up = make_prices(days=300, drift=0.004)["Close"]
    s = scanner.stats(up)
    assert s["Trend"] == "Uptrend"
    assert s["1D"] == pytest.approx(up.iloc[-1] / up.iloc[-2] - 1)
    assert 0 <= s["RSI"] <= 100 and s["From 52w high"] <= 0
    t = scanner.table({"UP": up, "SHORT": up.iloc[:10]})
    assert list(t.index) == ["UP"]


def test_scan_reads_one_batch_download(monkeypatch):
    a = make_prices(days=300, seed=1)
    b = make_prices(days=300, seed=2, tz="Asia/Kolkata")
    frame = pd.concat({"AAPL": a.tz_localize(None), "TCS.NS": b.tz_localize(None)}, axis=1)
    calls = []

    def fake_download(tickers, **kw):
        calls.append(tickers)
        return frame

    monkeypatch.setattr(scanner.yf, "download", fake_download)
    result, failed = scanner.scan(["aapl", "TCS.NS", "GONE.NS"])
    assert calls == [["AAPL", "TCS.NS", "GONE.NS"]]
    assert set(result.index) == {"AAPL", "TCS.NS"} and failed == ["GONE.NS"]
    assert np.isfinite(result.loc["AAPL", "1M"])


# ---------------------------------------------------------------- search --

def test_search_parse_filters_markets_and_types():
    quotes = [
        {"symbol": "ETERNAL.NS", "longname": "Eternal Limited", "quoteType": "EQUITY", "exchDisp": "NSE"},
        {"symbol": "543320.BO", "shortname": "ETERNAL LTD", "quoteType": "EQUITY", "exchDisp": "Bombay"},
        {"symbol": "BRK-B", "shortname": "Berkshire B", "quoteType": "EQUITY", "exchDisp": "NYSE"},
        {"symbol": "VOD.L", "shortname": "Vodafone", "quoteType": "EQUITY", "exchDisp": "London"},
        {"symbol": "BTC-USD", "shortname": "Bitcoin", "quoteType": "CRYPTOCURRENCY"},
        {"symbol": "SPY", "shortname": "SPDR S&P 500", "quoteType": "ETF", "exchDisp": "NYSEArca"},
    ]
    out = search.parse(quotes)
    assert [q["symbol"] for q in out] == ["ETERNAL.NS", "543320.BO", "BRK-B", "SPY"]
    assert out[0] == {"symbol": "ETERNAL.NS", "name": "Eternal Limited", "exchange": "NSE"}
    assert len(search.parse(quotes, limit=2)) == 2
    assert search.search("   ") == []


def test_headline_adds_filing_detail_and_group_explainer():
    filing = _item("Outcome of Board Meeting", ["meeting"], kind="filing")
    filing.detail = "Board approved results and an interim dividend"
    assert impact.headline(filing) == "Outcome of Board Meeting: Board approved results and an interim dividend"
    assert impact.headline(_item("Q2 profit rises", ["earnings"])) == "Q2 profit rises"

    items = [_item("Beat", ["earnings"], sentiment=1), _item("Miss", ["earnings"], sentiment=-1)]
    labels = [lbl for lbl, _ in impact.explain_group("earnings", items)]
    assert labels == ["", "When it's good", "When it's bad"]
    assert [lbl for lbl, _ in impact.explain_group(RED_FLAG, items)] == [""]


def test_cli_scan(monkeypatch, capsys):
    from stocklens import cli
    frame = pd.concat({"AAPL": make_prices(days=300, seed=1).tz_localize(None),
                       "MSFT": make_prices(days=300, seed=2).tz_localize(None)}, axis=1)
    monkeypatch.setattr(scanner.yf, "download", lambda tickers, **kw: frame)
    assert cli.main(["--scan", "us"]) == 0
    out = capsys.readouterr().out
    assert "AAPL" in out and "MSFT" in out and "Skipped (no data)" in out
    with pytest.raises(SystemExit):
        cli.main([])

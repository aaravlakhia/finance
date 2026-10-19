"""Build one combined report for a stock."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from . import briefing, filings, forecast, fundamentals, impact, marketdata, news, scorecard, signals, timeline
from .indicators import add_all
from .models import Item, Signal
from .symbols import Ticker, resolve
from .timeline import Move

log = logging.getLogger(__name__)

PERIODS = ["1mo", "3mo", "6mo", "1y", "2y", "5y"]
_WINDOW = {"1mo": pd.DateOffset(months=1), "3mo": pd.DateOffset(months=3),
           "6mo": pd.DateOffset(months=6), "1y": pd.DateOffset(years=1),
           "2y": pd.DateOffset(years=2), "5y": pd.DateOffset(years=5)}


class NoPriceData(Exception):
    pass


@dataclass
class Report:
    ticker: Ticker
    name: str
    profile: dict
    period: str
    history: pd.DataFrame          # full history with indicators (used for calculations)
    prices: pd.DataFrame           # the requested display window
    signals: list[Signal]
    score: int
    verdict: str
    performance: dict
    risk: dict
    quarterly: pd.DataFrame
    annual: pd.DataFrame
    upcoming: list[Item]
    timeline: list[Item]           # news + filings + past events, newest first
    moves: list[Move]
    warnings: list[str] = field(default_factory=list)
    # market context and the prediction lab
    benchmark: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    relative: dict | None = None
    cone: pd.DataFrame = field(default_factory=pd.DataFrame)
    ranges: pd.DataFrame = field(default_factory=pd.DataFrame)
    analogs: dict | None = None
    track: dict | None = None
    backtest: dict | None = None
    # investment checklist and the plain-English summary
    pillars: list = field(default_factory=list)
    checklist_score: float | None = None
    checklist_label: str = ""
    briefing: list[str] = field(default_factory=list)
    # how each kind of news has moved this stock (see impact.py)
    topic_stats: dict = field(default_factory=dict)

    @property
    def red_flags(self) -> list[Item]:
        """Red flags within the chart period (older ones stay in the timeline)."""
        start = self.prices.index[0]
        return [i for i in self.timeline if i.red_flag and i.when >= start]

    @property
    def last_close(self) -> float:
        return float(self.history["Close"].iloc[-1])

    @property
    def dividend_yield(self) -> float | None:
        """Dividends paid over the last 12 months divided by the current price."""
        if "Dividends" not in self.history:
            return None
        year = self.history[self.history.index >= self.history.index[-1] - pd.DateOffset(years=1)]
        total = year["Dividends"].sum()
        return total / self.last_close if total > 0 else None


def _safe(label: str, fn, warnings: list[str], default):
    try:
        return fn()
    except Exception as exc:
        log.debug("%s failed", label, exc_info=True)
        warnings.append(f"{label} unavailable ({exc.__class__.__name__})")
        return default


def build(symbol: str, market: str | None = None, period: str = "1y",
          include_news: bool = True, include_filings: bool = True, news_limit: int = 60) -> Report:
    if period not in PERIODS:
        raise ValueError(f"period must be one of {', '.join(PERIODS)}")
    ticker = resolve(symbol, market)
    yt = yf.Ticker(ticker.yahoo)
    warnings: list[str] = []

    # Extra history before the display window feeds the 200-day average, the
    # "similar setups" statistics and the backtest.
    fetch_period = "10y" if period == "5y" else "5y"
    try:
        hist = marketdata.history(yt, fetch_period)
    except Exception as exc:
        log.debug("price history failed", exc_info=True)
        raise NoPriceData(f"Couldn't download prices for {ticker.yahoo} from Yahoo Finance "
                          f"({exc.__class__.__name__}). Check your internet connection and try again.") from exc
    if hist.empty:
        hint = "" if ticker.market.code == "IN" else " Indian stocks need .NS / .BO or --market in."
        raise NoPriceData(f"No price data for {ticker.yahoo}. Check the symbol.{hint}")
    hist = add_all(hist)
    start = hist.index[-1] - _WINDOW[period]
    prices = hist[hist.index >= start]

    prof = _safe("Company profile", lambda: marketdata.profile(yt), warnings, {})
    full_name = prof.get("longName") or prof.get("shortName") or ticker.base
    name = marketdata.search_name(full_name)

    # News and filings come from other sites, so fetch them while we talk to Yahoo.
    with ThreadPoolExecutor(max_workers=2) as pool:
        news_job = pool.submit(news.fetch, name, ticker, news_limit) if include_news else None
        # Filings for the whole history give the news-impact statistics more to work with.
        filings_job = pool.submit(filings.fetch, ticker, hist.index[0]) if include_filings else None

        quarterly, annual, fin_warnings = fundamentals.fetch(yt)
        warnings += fin_warnings
        upcoming = _safe("Upcoming events", lambda: marketdata.upcoming_events(yt, ticker), warnings, [])
        earnings = _safe("Earnings history", lambda: marketdata.past_earnings(yt, ticker), warnings, [])
        yahoo_items = (_safe("Yahoo news", lambda: marketdata.yahoo_news(yt), warnings, [])
                       if include_news else [])
        bench = _safe(f"{ticker.market.benchmark_name} index",
                      lambda: marketdata.history(yf.Ticker(ticker.market.benchmark), fetch_period)["Close"],
                      warnings, pd.Series(dtype=float))

        google_items, news_warnings = news_job.result() if news_job else ([], [])
        filing_items, filing_warnings = filings_job.result() if filings_job else ([], [])
    warnings += news_warnings + filing_warnings

    news_items = news.merge([yahoo_items, google_items], news_limit)
    events = earnings + marketdata.corporate_actions(hist)
    items = news_items + filing_items + events
    timeline.attach_reactions(items, hist, ticker.market)
    items.sort(key=lambda i: i.when, reverse=True)

    sigs = signals.price_signals(hist)
    sigs += signals.fundamental_signals(quarterly, "quarterly")
    score, verdict = signals.overall(sigs)

    close = hist["Close"]
    r = Report(
        ticker=ticker, name=full_name, profile=prof, period=period, history=hist, prices=prices,
        signals=sigs, score=score, verdict=verdict, performance=signals.performance(hist),
        risk=signals.risk_stats(hist), quarterly=quarterly, annual=annual, upcoming=upcoming,
        timeline=items, moves=timeline.biggest_moves(prices, items, ticker.market),
        warnings=warnings, benchmark=bench, relative=signals.relative(close, bench),
        cone=forecast.cone(close), ranges=forecast.ranges(close), analogs=forecast.analogs(hist),
        track=forecast.track_record(hist), backtest=forecast.trend_backtest(hist),
    )
    r.pillars = scorecard.evaluate(r)
    r.checklist_score, r.checklist_label = scorecard.overall(r.pillars)
    r.topic_stats = impact.history(items, hist)
    r.briefing = briefing.summarize(r)
    return r

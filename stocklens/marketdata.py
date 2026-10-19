"""Price history, company profile and calendar events from Yahoo Finance (via yfinance)."""

import logging
from datetime import date, datetime

import pandas as pd

from .classify import classify
from .models import Item
from .symbols import Ticker

log = logging.getLogger(__name__)

PROFILE_KEYS = [
    "longName", "shortName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
    "priceToBook", "dividendYield", "currency", "financialCurrency", "exchange", "website",
    "longBusinessSummary", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "beta",
    # quality and health (fractions, except debtToEquity which Yahoo gives in percent)
    "profitMargins", "returnOnEquity", "revenueGrowth", "earningsGrowth", "debtToEquity",
    "currentRatio", "freeCashflow",
    # analysts and ownership
    "targetMeanPrice", "targetHighPrice", "targetLowPrice", "recommendationKey",
    "numberOfAnalystOpinions", "heldPercentInsiders", "heldPercentInstitutions",
]

_NAME_SUFFIXES = (
    " limited", " ltd.", " ltd", " inc.", " inc", " incorporated", " corporation", " corp.",
    " corp", " company", " & co.", " & co", " co.", " plc", " holdings", " group", ",",
)


def search_name(full_name: str) -> str:
    """'Infosys Limited' -> 'Infosys', 'Apple Inc.' -> 'Apple' (better news search)."""
    name = full_name.strip()
    if name.lower().startswith("the "):
        name = name[4:]
    changed = True
    while changed:
        changed = False
        for suffix in _NAME_SUFFIXES:
            if name.lower().endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)].rstrip(" ,&")
                changed = True
    return name or full_name


def profile(yt) -> dict:
    info = yt.info or {}
    return {k: info.get(k) for k in PROFILE_KEYS}


def history(yt, period: str) -> pd.DataFrame:
    df = yt.history(period=period, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.dropna(subset=["Close"])


def _to_timestamp(value, tz: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize(tz) if ts.tzinfo is None else ts


def upcoming_events(yt, ticker: Ticker) -> list[Item]:
    """Next earnings date and dividend dates from Yahoo's calendar."""
    tz = ticker.market.timezone
    cal = yt.calendar or {}
    items = []
    today = pd.Timestamp.now(tz=tz).normalize()
    for d in cal.get("Earnings Date") or []:
        when = _to_timestamp(d, tz)
        if when >= today:
            est = cal.get("Earnings Average")
            detail = f"EPS estimate {est:.2f}" if isinstance(est, (int, float)) else ""
            items.append(Item(when, "Earnings announcement", "Yahoo calendar", "event",
                              detail=detail, tags=["earnings"], has_time=False))
            break
    for key, title in (("Ex-Dividend Date", "Ex-dividend date"), ("Dividend Date", "Dividend payment")):
        d = cal.get(key)
        if isinstance(d, (date, datetime)):
            when = _to_timestamp(d, tz)
            if when >= today:
                items.append(Item(when, title, "Yahoo calendar", "event",
                                  tags=["dividend/buyback"], has_time=False))
    return sorted(items, key=lambda i: i.when)


def past_earnings(yt, ticker: Ticker) -> list[Item]:
    """Reported earnings with the surprise vs analyst estimates."""
    df = yt.get_earnings_dates(limit=12)
    if df is None or df.empty:
        return []
    items = []
    now = pd.Timestamp.now(tz=ticker.market.timezone)
    for when, row in df.iterrows():
        when = _to_timestamp(when, ticker.market.timezone)
        reported = pd.to_numeric(row.get("Reported EPS"), errors="coerce")
        if when > now or pd.isna(reported):
            continue
        estimate = pd.to_numeric(row.get("EPS Estimate"), errors="coerce")
        surprise = pd.to_numeric(row.get("Surprise(%)"), errors="coerce")
        if pd.notna(surprise):
            verdict = "beat" if surprise > 0 else "missed" if surprise < 0 else "matched"
            title = f"Earnings {verdict} estimates (EPS {reported:.2f} vs {estimate:.2f}, {surprise:+.1f}%)"
            sentiment = (surprise > 0) - (surprise < 0)
        else:
            title = f"Earnings reported (EPS {reported:.2f})"
            sentiment = 0
        items.append(Item(when, title, "Yahoo earnings", "event", tags=["earnings"],
                          sentiment=int(sentiment), has_time=when.time() != datetime.min.time()))
    return items


def corporate_actions(prices: pd.DataFrame) -> list[Item]:
    """Dividends and splits that already appear in the price history."""
    items = []
    if "Dividends" in prices:
        for when, amount in prices.loc[prices["Dividends"] > 0, "Dividends"].items():
            items.append(Item(when, f"Ex-dividend ({amount:.2f} per share)", "Price history", "event",
                              tags=["dividend/buyback"], has_time=False))
    if "Stock Splits" in prices:
        for when, ratio in prices.loc[prices["Stock Splits"] > 0, "Stock Splits"].items():
            items.append(Item(when, f"Stock split ({ratio:g}-for-1)", "Price history", "event",
                              tags=["dividend/buyback"], has_time=False))
    return items


def yahoo_news(yt) -> list[Item]:
    return parse_yahoo_news(yt.news or [])


def parse_yahoo_news(raw: list[dict]) -> list[Item]:
    """Handle both the current ('content' wrapper) and older yfinance news formats."""
    items = []
    for article in raw:
        c = article.get("content") or article
        title = c.get("title")
        if not title:
            continue
        when = c.get("pubDate") or c.get("displayTime")
        if when:
            when = pd.Timestamp(when)
        elif article.get("providerPublishTime"):
            when = pd.Timestamp(article["providerPublishTime"], unit="s")
        else:
            continue
        if when.tzinfo is None:
            when = when.tz_localize("UTC")
        source = (c.get("provider") or {}).get("displayName") or article.get("publisher") or "Yahoo Finance"
        url = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
               or article.get("link") or "")
        summary = c.get("summary") or ""
        tags, sentiment, red = classify(title)
        items.append(Item(when, title, source, "news", url=url, detail=summary,
                          tags=tags, sentiment=sentiment, red_flag=red))
    return items

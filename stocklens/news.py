"""Company news from Google News RSS (free, no API key) plus Yahoo Finance."""

import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

from .classify import classify
from .models import Item
from .symbols import Ticker

log = logging.getLogger(__name__)

GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stocklens/0.1)"}


def queries(name: str, ticker: Ticker) -> list[str]:
    """General news, possible scandals, and meetings/results - three searches per company."""
    q = f'"{name}"'
    general = f"{q} share price" if ticker.market.code == "IN" else f"{q} stock"
    return [
        general,
        f"{q} (fraud OR probe OR investigation OR lawsuit OR scam OR penalty OR raid OR allegations)",
        f'{q} (AGM OR "annual general meeting" OR "shareholders meeting" OR "board meeting" '
        f"OR results OR earnings OR dividend)",
    ]


def google_news(query: str, ticker: Ticker, timeout: float = 10) -> list[Item]:
    hl, gl, ceid = ticker.market.news_locale
    resp = requests.get(GOOGLE_NEWS_URL, params={"q": query, "hl": hl, "gl": gl, "ceid": ceid},
                        headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return parse_google_rss(resp.content)


def parse_google_rss(xml: bytes) -> list[Item]:
    root = ET.fromstring(xml)
    items = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        pub = node.findtext("pubDate")
        if not title or not pub:
            continue
        src = node.find("source")
        source = (src.text or "").strip() if src is not None else ""
        # Google appends " - Publisher" to every title.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            when = pd.Timestamp(parsedate_to_datetime(pub))
        except (TypeError, ValueError):
            continue
        when = when.tz_localize("UTC") if when.tzinfo is None else when.tz_convert("UTC")
        tags, sentiment, red = classify(title)
        items.append(Item(when, title, source or "Google News", "news",
                          url=node.findtext("link") or "", tags=tags,
                          sentiment=sentiment, red_flag=red))
    return items


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:80]


def is_relevant(title: str, name: str, ticker: Ticker) -> bool:
    """Drop search hits that don't mention the company at all."""
    # Whole-word matches only, so "Apple" doesn't match "Pineapple".
    words = name.split()
    needles = [name, " ".join(words[:2])]
    if len(ticker.base) >= 2:
        needles.append(ticker.base)
    return any(re.search(rf"\b{re.escape(n)}\b", title, re.IGNORECASE) for n in needles if n)


def merge(groups: list[list[Item]], limit: int) -> list[Item]:
    """De-duplicate by headline, newest first. Red flags are kept even past the limit."""
    seen, merged = set(), []
    for item in sorted((i for g in groups for i in g), key=lambda i: i.when, reverse=True):
        k = _key(item.title)
        if k not in seen:
            seen.add(k)
            merged.append(item)
    return merged[:limit] + [i for i in merged[limit:] if i.red_flag]


def fetch(name: str, ticker: Ticker, limit: int = 60) -> tuple[list[Item], list[str]]:
    groups, warnings = [], []
    for q in queries(name, ticker):
        try:
            hits = google_news(q, ticker)
            groups.append([i for i in hits if is_relevant(i.title, name, ticker)])
        except Exception as exc:
            log.debug("Google News query failed: %s", q, exc_info=True)
            warnings.append(f"Google News search failed ({exc.__class__.__name__})")
            break
    return merge(groups, limit), warnings

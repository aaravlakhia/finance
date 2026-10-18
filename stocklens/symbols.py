"""Turn what the user types into a Yahoo Finance symbol and the market it trades on."""

import re
from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class Market:
    code: str
    name: str
    currency: str
    currency_sign: str
    timezone: str
    close_time: time
    # Google News locale parameters: (hl, gl, ceid)
    news_locale: tuple[str, str, str]


US = Market("US", "United States", "USD", "$", "America/New_York", time(16, 0),
            ("en-US", "US", "US:en"))
INDIA = Market("IN", "India", "INR", "₹", "Asia/Kolkata", time(15, 30),
               ("en-IN", "IN", "IN:en"))


@dataclass(frozen=True)
class Ticker:
    yahoo: str      # symbol Yahoo Finance understands, e.g. "INFY.NS"
    base: str       # symbol without exchange suffix, e.g. "INFY"
    exchange: str   # "US", "NSE" or "BSE"
    market: Market


_PREFIXES = {"NSE": "nse", "BSE": "bse", "NASDAQ": "us", "NYSE": "us", "US": "us"}


def resolve(text: str, market: str | None = None) -> Ticker:
    """Work out the exchange for a symbol.

    Accepted forms: ``AAPL``, ``INFY.NS``, ``RELIANCE.BO``, ``NSE:TCS``,
    ``BSE:500325``, or a bare symbol plus ``market`` ("us", "in"/"nse", "bse").
    Six-digit numbers are treated as BSE scrip codes.
    """
    s = text.strip().upper()
    if not s:
        raise ValueError("Empty symbol")
    if ":" in s:
        prefix, s = s.split(":", 1)
        market = _PREFIXES.get(prefix, market)

    if s.endswith(".NS"):
        return Ticker(s, s[:-3], "NSE", INDIA)
    if s.endswith(".BO"):
        return Ticker(s, s[:-3], "BSE", INDIA)

    m = (market or "").lower()
    if m in ("in", "india", "nse"):
        return Ticker(f"{s}.NS", s, "NSE", INDIA)
    if m == "bse" or re.fullmatch(r"\d{6}", s):
        return Ticker(f"{s}.BO", s, "BSE", INDIA)

    # Share classes: Yahoo writes BRK.B as BRK-B.
    if re.fullmatch(r"[A-Z]+\.[A-Z]", s):
        s = s.replace(".", "-")
    return Ticker(s, s, "US", US)

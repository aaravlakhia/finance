"""Official company filings: SEC EDGAR (US) and NSE corporate announcements (India).

These are where shareholder meetings, results, management changes and legal or
accounting problems are formally disclosed - often before or alongside the news.
"""

import json
import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

from .classify import RED_FLAG, classify
from .models import Item
from .symbols import Ticker

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("STOCKLENS_CACHE", Path.home() / ".cache" / "stocklens"))

# ---------------------------------------------------------------- SEC (US) --

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# The SEC asks automated tools to identify themselves with a contact email.
SEC_USER_AGENT = os.environ.get("STOCKLENS_SEC_USER_AGENT", "stocklens/0.1 stocklens-user@example.com")

# 8-K item number -> (plain description, tags, red flag)
EIGHT_K_ITEMS = {
    "1.01": ("Signed a material agreement", ["deal"], False),
    "1.02": ("Ended a material agreement", ["deal"], False),
    "1.03": ("Bankruptcy or receivership", [RED_FLAG], True),
    "1.05": ("Material cybersecurity incident", [RED_FLAG], True),
    "2.01": ("Completed an acquisition or sale of assets", ["deal"], False),
    "2.02": ("Results of operations (earnings release)", ["earnings"], False),
    "2.03": ("Took on a material debt obligation", [], False),
    "2.04": ("Event that accelerates a debt obligation", [RED_FLAG], True),
    "2.05": ("Restructuring / exit costs (e.g. layoffs)", [], False),
    "2.06": ("Material impairment (write-down)", [], False),
    "3.01": ("Delisting notice or failed listing rule", [RED_FLAG], True),
    "3.02": ("Unregistered sale of shares", [], False),
    "3.03": ("Change to shareholders' rights", [], False),
    "4.01": ("Changed auditor", [RED_FLAG], True),
    "4.02": ("Past financial statements can no longer be relied on", [RED_FLAG], True),
    "5.01": ("Change in control of the company", ["deal"], False),
    "5.02": ("Director or officer departure/appointment", ["management"], False),
    "5.03": ("Amended bylaws or changed fiscal year", [], False),
    "5.07": ("Shareholder meeting vote results", ["meeting"], False),
    "7.01": ("Regulation FD disclosure", [], False),
    "8.01": ("Other material event", [], False),
}

# Form type -> (plain description, tags, red flag)
SEC_FORMS = {
    "10-Q": ("Quarterly report", ["earnings"], False),
    "10-K": ("Annual report", ["earnings"], False),
    "20-F": ("Annual report (foreign issuer)", ["earnings"], False),
    "6-K": ("Current report (foreign issuer)", [], False),
    "DEF 14A": ("Proxy statement - annual shareholder meeting", ["meeting"], False),
    "DEFA14A": ("Additional proxy material for shareholder meeting", ["meeting"], False),
    "NT 10-K": ("Notice of late annual report", [RED_FLAG], True),
    "NT 10-Q": ("Notice of late quarterly report", [RED_FLAG], True),
    "SC 13D": ("Investor disclosed an active stake over 5%", ["deal"], False),
    "SCHEDULE 13D": ("Investor disclosed an active stake over 5%", ["deal"], False),
}


def _cached_json(name: str, url: str, max_age_days: float, headers: dict) -> dict:
    path = CACHE_DIR / name
    try:
        if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
            return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    except OSError:
        pass
    return data


def sec_cik(symbol: str) -> int | None:
    data = _cached_json("sec_company_tickers.json", SEC_TICKERS_URL, 7, {"User-Agent": SEC_USER_AGENT})
    for row in data.values():
        if row.get("ticker", "").upper() == symbol.upper():
            return int(row["cik_str"])
    return None


def parse_sec_submissions(data: dict, since: pd.Timestamp) -> list[Item]:
    recent = data.get("filings", {}).get("recent", {})
    cik = int(data.get("cik", 0))
    forms = recent.get("form", [])
    items = []
    for i, form in enumerate(forms):
        def field(name, default=""):
            values = recent.get(name, [])
            return values[i] if i < len(values) else default

        if form == "8-K":
            codes = [c.strip() for c in field("items").split(",") if c.strip() and c.strip() != "9.01"]
            known = [EIGHT_K_ITEMS[c] for c in codes if c in EIGHT_K_ITEMS]
            description = "; ".join(k[0] for k in known) or "Current report"
            tags = sorted({t for k in known for t in k[1]})
            red = any(k[2] for k in known)
        elif form in SEC_FORMS:
            description, tags, red = SEC_FORMS[form]
        else:
            continue

        # EDGAR's acceptanceDateTime ends in "Z" but is actually US Eastern time.
        accepted = field("acceptanceDateTime")
        if accepted:
            when = pd.Timestamp(accepted.rstrip("Z").split(".")[0]).tz_localize("America/New_York")
            has_time = True
        else:
            when = pd.Timestamp(field("filingDate")).tz_localize("America/New_York")
            has_time = False
        if when < since:
            continue
        accession = field("accessionNumber").replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{field('primaryDocument')}"
        items.append(Item(when, description, f"SEC {form}", "filing", url=url, tags=list(tags),
                          sentiment=-1 if red else 0, red_flag=red, has_time=has_time))
    return items


def sec_filings(symbol: str, since: pd.Timestamp) -> list[Item]:
    cik = sec_cik(symbol)
    if cik is None:
        return []
    resp = requests.get(SEC_SUBMISSIONS_URL.format(cik=cik), timeout=20,
                        headers={"User-Agent": SEC_USER_AGENT})
    resp.raise_for_status()
    return parse_sec_submissions(resp.json(), since)


# ------------------------------------------------------------ NSE (India) --

NSE_HOME = "https://www.nseindia.com/"
NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"


def _nse_session():
    # NSE blocks plain scripted clients; curl_cffi (installed with yfinance)
    # presents a normal browser fingerprint.
    try:
        from curl_cffi import requests as browser_requests
        return browser_requests.Session(impersonate="chrome")
    except ImportError:
        s = requests.Session()
        s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        return s


def parse_nse_announcements(data, since: pd.Timestamp) -> list[Item]:
    rows = data.get("data", []) if isinstance(data, dict) else data
    items = []
    for row in rows or []:
        subject = (row.get("desc") or "").strip()
        text = " ".join((row.get("attchmntText") or "").split())
        if not subject and not text:
            continue
        stamp = row.get("sort_date") or row.get("an_dt")
        try:
            when = pd.Timestamp(stamp).tz_localize("Asia/Kolkata")
        except (TypeError, ValueError):
            continue
        if pd.isna(when) or when < since:
            continue
        tags, sentiment, red = classify(f"{subject}. {text}")
        detail = text if len(text) <= 300 else text[:297] + "..."
        items.append(Item(when, subject or detail[:80], "NSE filing", "filing",
                          url=row.get("attchmntFile") or "", detail=detail, tags=tags,
                          sentiment=sentiment, red_flag=red))
    return items


def nse_announcements(symbol: str, since: pd.Timestamp) -> list[Item]:
    session = _nse_session()
    session.get(NSE_HOME, timeout=15)  # sets the cookies the API requires
    resp = session.get(NSE_ANNOUNCEMENTS_URL, params={"index": "equities", "symbol": symbol},
                       headers={"Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}"},
                       timeout=20)
    resp.raise_for_status()
    return parse_nse_announcements(resp.json(), since)


def fetch(ticker: Ticker, since: pd.Timestamp) -> tuple[list[Item], list[str]]:
    try:
        if ticker.market.code == "US":
            return sec_filings(ticker.base, since), []
        if not ticker.base.isdigit():  # NSE symbols can contain & and - (M&M, BAJAJ-AUTO)
            return nse_announcements(ticker.base, since), []
        return [], ["Filings: use the NSE symbol (e.g. INFY.NS) to see exchange announcements"]
    except Exception as exc:
        log.debug("filings fetch failed", exc_info=True)
        source = "SEC EDGAR" if ticker.market.code == "US" else "NSE"
        return [], [f"{source} filings unavailable ({exc.__class__.__name__})"]

"""Find any US or Indian stock by company name or symbol (Yahoo Finance search)."""

import re

import yfinance as yf

ALLOWED_TYPES = {"EQUITY", "ETF"}


def is_supported(symbol: str) -> bool:
    """US symbols have no exchange suffix (share classes use '-'); Indian ones end in .NS or .BO."""
    return symbol.endswith((".NS", ".BO")) or bool(re.fullmatch(r"[A-Z0-9^][A-Z0-9-]*", symbol))


def parse(quotes: list[dict], limit: int = 10) -> list[dict]:
    out = []
    for q in quotes:
        symbol = (q.get("symbol") or "").upper()
        if not symbol or q.get("quoteType") not in ALLOWED_TYPES or not is_supported(symbol):
            continue
        name = q.get("longname") or q.get("shortname") or symbol
        exchange = q.get("exchDisp") or q.get("exchange") or ""
        out.append({"symbol": symbol, "name": name, "exchange": exchange})
        if len(out) >= limit:
            break
    return out


def search(query: str, limit: int = 10) -> list[dict]:
    """[{symbol, name, exchange}, ...] for US and Indian listings matching `query`."""
    query = query.strip()
    if not query:
        return []
    found = yf.Search(query, max_results=25, news_count=0, lists_count=0, enable_fuzzy_query=True,
                      raise_errors=False)
    return parse(found.quotes or [], limit)

"""Command line: python -m stocklens AAPL  |  python -m stocklens INFY TCS -m in"""

import argparse
import logging
import sys
import textwrap

from . import DISCLAIMER, fmt
from .report import PERIODS, NoPriceData, Report, build
from .timeline import is_unusual

WIDTH = 78
TONE = {1: "+", -1: "-", 0: "·"}


def _rule(title: str = "") -> str:
    return f"── {title} ".ljust(WIDTH, "─") if title else "─" * WIDTH


def _wrap(text: str, indent: int) -> str:
    return textwrap.fill(text, WIDTH, initial_indent="", subsequent_indent=" " * indent)


def _item_line(item, r: Report) -> str:
    m = r.ticker.market
    flag = "!" if item.red_flag else TONE[item.sentiment]
    tags = f"[{', '.join(item.tags[:2])}] " if item.tags else ""
    reaction = ""
    if item.reaction is not None:
        reaction = f"  -> {fmt.pct(item.reaction)}"
        if is_unusual(item.reaction, r.prices):
            reaction += " (big move)"
    day = item.when.tz_convert(m.timezone).strftime("%Y-%m-%d")
    return _wrap(f"{flag} {day} {tags}{item.title} ({item.source}){reaction}", 13)


def format_report(r: Report, news_count: int = 15) -> str:
    m = r.ticker.market
    p = r.profile
    out = []
    head = f"{r.name} ({r.ticker.yahoo})"
    sub = " · ".join(x for x in (r.ticker.exchange, m.name, p.get("sector"), p.get("industry")) if x)
    out += ["═" * WIDTH, head, sub, "═" * WIDTH]

    perf = r.performance
    out.append(f"Price {fmt.price(r.last_close, m)} ({fmt.pct(perf.get('1D'))} today)   "
               f"52w range {fmt.price(r.risk['low_52w'], m)} - {fmt.price(r.risk['high_52w'], m)}")
    facts = [f"Market cap {fmt.money(p.get('marketCap'), m)}"]
    if p.get("trailingPE"):
        facts.append(f"P/E {fmt.number(p['trailingPE'], 1)}")
    if r.dividend_yield:
        facts.append(f"Div yield {fmt.pct(r.dividend_yield, signed=False)}")
    facts.append(f"Volatility {fmt.pct(r.risk['volatility'], signed=False)}/yr")
    out.append("   ".join(facts))
    out.append("Performance: " + " | ".join(f"{k} {fmt.pct(v)}" for k, v in perf.items()))

    out += ["", _rule(f"TREND  {r.verdict} (score {r.score:+d})")]
    for s in r.signals:
        out.append(_wrap(f"  {TONE[s.tone]} {s.text}", 4))

    if not r.quarterly.empty:
        out += ["", _rule("FINANCIALS (quarterly)")]
        out.append(f"  {'Quarter':<10}{'Revenue':>18}{'Net profit':>18}{'Margin':>9}{'EPS':>9}{'Rev chg':>10}")
        for when, row in r.quarterly.tail(5).iterrows():
            out.append(f"  {when:%Y-%m}   {fmt.money(row.get('Revenue'), m):>18}"
                       f"{fmt.money(row.get('Net profit'), m):>18}"
                       f"{fmt.pct(row.get('Net margin'), signed=False):>9}"
                       f"{fmt.number(row.get('EPS')):>9}{fmt.pct(row.get('Revenue growth')):>10}")

    if r.upcoming:
        out += ["", _rule("COMING UP")]
        for e in r.upcoming:
            when = e.when.tz_convert(m.timezone).strftime("%Y-%m-%d")
            out.append(f"  {when}  {e.title}" + (f" ({e.detail})" if e.detail else ""))

    flags = r.red_flags
    out += ["", _rule(f"RED FLAGS ({len(flags)})")]
    if flags:
        out += [_item_line(i, r) for i in flags[:8]]
    else:
        out.append("  None found in recent news and filings.")

    if r.moves:
        out += ["", _rule("BIGGEST MOVES & POSSIBLE CAUSES")]
        for mv in r.moves:
            out.append(f"  {mv.day}  {fmt.pct(mv.change):>8}" + ("" if mv.causes else "   (no matching news or filing)"))
            for c in mv.causes:
                out.append(_wrap(f"      <- {c.title} ({c.source})", 9))

    out += ["", _rule("TIMELINE (news, filings, events)")]
    if r.timeline:
        out += [_item_line(i, r) for i in r.timeline[:news_count]]
        out.append("  Legend: + positive  - negative  · neutral  ! red flag  -> price move that day")
    else:
        out.append("  Nothing found.")

    if r.warnings:
        out += ["", "Notes: " + "; ".join(dict.fromkeys(r.warnings))]
    out += ["", _wrap(DISCLAIMER, 0)]
    return "\n".join(out)


def format_watchlist(reports: list[Report]) -> str:
    rows = [f"{'Symbol':<14}{'Price':>14}{'1D':>9}{'1M':>9}{'1Y':>9}{'RSI':>6}  {'Trend':<17}{'Flags':>5}"]
    for r in reports:
        m = r.ticker.market
        rsi = r.history["RSI14"].iloc[-1]
        rows.append(f"{r.ticker.yahoo:<14}{fmt.price(r.last_close, m):>14}"
                    f"{fmt.pct(r.performance['1D']):>9}{fmt.pct(r.performance['1M']):>9}"
                    f"{fmt.pct(r.performance['1Y']):>9}{fmt.number(rsi, 0):>6}  "
                    f"{r.verdict:<17}{len(r.red_flags):>5}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="stocklens",
        description="Trend, financials, events, filings and news for US and Indian stocks.",
        epilog="Examples: stocklens AAPL | stocklens INFY.NS | stocklens TCS RELIANCE -m in | "
               "stocklens AAPL MSFT INFY.NS (watchlist)")
    ap.add_argument("symbols", nargs="+", help="e.g. AAPL, MSFT, INFY.NS, RELIANCE.BO, NSE:TCS")
    ap.add_argument("-m", "--market", choices=["us", "in", "nse", "bse"],
                    help="market for symbols without a suffix (default: us)")
    ap.add_argument("-p", "--period", default="1y", choices=PERIODS, help="chart window (default 1y)")
    ap.add_argument("-n", "--news", type=int, default=15, help="timeline items to show (default 15)")
    ap.add_argument("--no-news", action="store_true", help="skip news (faster)")
    ap.add_argument("--no-filings", action="store_true", help="skip SEC/NSE filings (faster)")
    ap.add_argument("--full", action="store_true", help="full report for every symbol in a watchlist")
    ap.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(message)s")
    if not args.verbose:
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # old Windows consoles can't print ₹

    reports, failed = [], 0
    for sym in args.symbols:
        try:
            reports.append(build(sym, args.market, args.period,
                                 include_news=not args.no_news, include_filings=not args.no_filings))
        except (NoPriceData, ValueError) as exc:
            print(f"{sym}: {exc}", file=sys.stderr)
            failed += 1

    if reports and (len(args.symbols) == 1 or args.full):
        print("\n\n".join(format_report(r, args.news) for r in reports))
    elif reports:
        print(format_watchlist(reports))
        print(f"\nRun `python -m stocklens {reports[0].ticker.yahoo}` for the full report.")
    return 1 if failed else 0

"""Turn the whole report into a short plain-English briefing."""

import pandas as pd

from . import fmt


def _pct(x: float) -> str:
    return f"{abs(x) * 100:.1f}%"


def summarize(r) -> list[str]:
    m = r.ticker.market
    out = []

    perf = r.performance
    day, year = perf.get("1D"), perf.get("1Y")
    s = f"{r.name} is at {fmt.price(r.last_close, m)}"
    if pd.notna(day):
        s += f", {'up' if day >= 0 else 'down'} {_pct(day)} today"
    if pd.notna(year):
        s += f" and {'up' if year >= 0 else 'down'} {_pct(year)} over the past year"
    if r.relative:
        gap = r.relative["gap"]
        if abs(gap) < 0.01:
            s += f", roughly in line with the {m.benchmark_name}"
        else:
            s += f", {'beating' if gap > 0 else 'lagging'} the {m.benchmark_name} by {abs(gap) * 100:.0f} points"
    out.append(s + ".")

    lead = next((sig.text for sig in r.signals if sig.group == "trend"), None)
    if lead:
        out.append(f"Trend: {r.verdict.lower()}. {lead}.")

    q = r.quarterly
    if not q.empty and "Revenue" in q and len(q["Revenue"].dropna()) >= 2:
        rev = q["Revenue"].dropna()
        change = rev.iloc[-1] / rev.iloc[-2] - 1
        s = f"Revenue {'grew' if change >= 0 else 'fell'} {_pct(change)} in the latest quarter"
        margin = q.get("Net margin", pd.Series(dtype=float)).dropna()
        if len(margin):
            s += f", with a net margin of {margin.iloc[-1]:.1%}"
        out.append(s + ".")

    flags = r.red_flags
    if flags:
        f = flags[0]
        day_s = f.when.tz_convert(m.timezone).strftime("%d %b %Y")
        count = "1 red flag" if len(flags) == 1 else f"{len(flags)} red flags"
        s = f'{count} in recent news and filings; the latest is "{f.title}" ({day_s}'
        if f.reaction is not None:
            s += f", stock {fmt.pct(f.reaction)} that day"
        out.append(s + ").")
    else:
        out.append("No red flags in recent news and filings.")

    if r.upcoming:
        e = r.upcoming[0]
        out.append(f"Coming up: {e.title.lower()} on {e.when.tz_convert(m.timezone):%d %b %Y}.")

    if r.ranges is not None and not r.ranges.empty:
        one = r.ranges.loc["1 month"]
        out.append(f"Based on how much it usually moves, a month from now it is likely (50%) to be between "
                   f"{fmt.price(one['low50'], m)} and {fmt.price(one['high50'], m)}, and very likely (90%) "
                   f"between {fmt.price(one['low90'], m)} and {fmt.price(one['high90'], m)}.")

    if r.analogs:
        row = r.analogs["rows"][0]
        s = (f"After past days like today ({r.analogs['setup']}), it was higher {row['horizon']} later "
             f"{row['pct_higher']:.0%} of the time (median {fmt.pct(row['median'])})")
        if r.track:
            s += (f"; on this stock's history that method was right {r.track['accuracy']:.0%} of the time, "
                  f"vs {r.track['always_up']:.0%} for always guessing 'up'")
        out.append(s + ".")

    if r.checklist_score is not None:
        out.append(f"Investment checklist: {r.checklist_score:.1f}/10 ({r.checklist_label.lower()}).")
    return out

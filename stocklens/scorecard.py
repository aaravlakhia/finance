"""An investment checklist: six pillars scored 0-10, each with its reasons.

The thresholds are common rules of thumb, not universal truths. A fast-growing
company can deserve a high P/E, and debt ratios mean little for banks, so
always read the reasons, not just the number.
"""

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Pillar:
    name: str
    question: str
    score: float | None = None
    reasons: list[str] = field(default_factory=list)


def _band(value, cuts, scores):
    """Map value to a score: cuts are ascending upper bounds, scores has one extra entry."""
    for cut, score in zip(cuts, scores):
        if value < cut:
            return score
    return scores[-1]


def _num(value):
    return None if value is None or pd.isna(value) else float(value)


def _clamp(x):
    return max(0.0, min(10.0, x))


def trend(r) -> Pillar:
    p = Pillar("Trend", "Is the price moving the right way?")
    h = r.history
    last = h.iloc[-1]
    pts = 0
    if pd.notna(last["SMA200"]):
        if last["Close"] > last["SMA200"]:
            pts += 3
            p.reasons.append("Above its 200-day average (long-term uptrend)")
        else:
            p.reasons.append("Below its 200-day average (long-term downtrend)")
        if last["SMA50"] > last["SMA200"]:
            pts += 2
            p.reasons.append("50-day average above the 200-day")
    six = r.performance.get("6M")
    if six is not None and pd.notna(six):
        if six > 0:
            pts += 2
        p.reasons.append(f"{six:+.0%} over 6 months")
    rsi = last.get("RSI14")
    if pd.notna(rsi) and 40 <= rsi <= 70:
        pts += 1
        p.reasons.append(f"Healthy momentum (RSI {rsi:.0f})")
    elif pd.notna(rsi):
        p.reasons.append(f"RSI {rsi:.0f} is {'stretched' if rsi > 70 else 'weak'}")
    if last["Close"] >= 0.9 * r.risk["high_52w"]:
        pts += 2
        p.reasons.append("Within 10% of its 52-week high")
    p.score = float(pts)
    return p


def growth(r) -> Pillar:
    p = Pillar("Growth", "Are sales and profits growing?")
    scores = []
    rev = _num(r.profile.get("revenueGrowth"))
    if rev is None and not r.annual.empty and "Revenue growth" in r.annual:
        g = r.annual["Revenue growth"].dropna()
        rev = float(g.iloc[-1]) if len(g) else None
    if rev is not None:
        scores.append(_band(rev, [0, 0.05, 0.10, 0.20], [2, 4, 6, 8, 10]))
        p.reasons.append(f"Revenue growth {rev:+.0%} year on year")
    earn = _num(r.profile.get("earningsGrowth"))
    if earn is not None:
        scores.append(_band(earn, [0, 0.05, 0.10, 0.20], [2, 4, 6, 8, 10]))
        p.reasons.append(f"Earnings growth {earn:+.0%} year on year")
    p.score = sum(scores) / len(scores) if scores else None
    return p


def profitability(r) -> Pillar:
    p = Pillar("Profitability", "Does it make good money on its sales and capital?")
    scores = []
    margin = _num(r.profile.get("profitMargins"))
    if margin is None and not r.quarterly.empty and "Net margin" in r.quarterly:
        m = r.quarterly["Net margin"].dropna()
        margin = float(m.iloc[-1]) if len(m) else None
    if margin is not None:
        scores.append(_band(margin, [0, 0.05, 0.10, 0.20], [1, 3, 5, 7, 9]))
        p.reasons.append(f"Net profit margin {margin:.1%}")
    roe = _num(r.profile.get("returnOnEquity"))
    if roe is not None:
        scores.append(_band(roe, [0, 0.08, 0.15, 0.25], [1, 3, 5, 8, 10]))
        p.reasons.append(f"Return on equity {roe:.1%}")
    p.score = sum(scores) / len(scores) if scores else None
    return p


def valuation(r) -> Pillar:
    p = Pillar("Valuation", "Is the price reasonable for what you get?")
    pe = _num(r.profile.get("trailingPE"))
    fpe = _num(r.profile.get("forwardPE"))
    if pe is None and fpe is None:
        return p
    if pe is None or pe <= 0:
        score = 2.0
        p.reasons.append("No positive earnings, so P/E isn't meaningful")
    else:
        score = float(_band(pe, [12, 18, 25, 35, 50], [9, 8, 6, 4, 3, 1]))
        p.reasons.append(f"P/E {pe:.1f} (rule of thumb: under 18 cheap, over 35 expensive)")
    if pe and fpe and 0 < fpe < pe:
        score += 1
        p.reasons.append(f"Forward P/E {fpe:.1f} is lower, so earnings are expected to grow")
    target = _num(r.profile.get("targetMeanPrice"))
    if target:
        upside = target / r.last_close - 1
        if upside > 0.15:
            score += 1
        elif upside < -0.05:
            score -= 1
        p.reasons.append(f"Average analyst target implies {upside:+.0%}")
    p.score = _clamp(score)
    return p


def health(r) -> Pillar:
    p = Pillar("Financial health", "Can it handle bad times?")
    scores = []
    if r.profile.get("sector") == "Financial Services":
        p.reasons.append("Debt ratios aren't meaningful for banks and lenders")
    else:
        de = _num(r.profile.get("debtToEquity"))
        if de is not None:
            scores.append(_band(de, [30, 80, 150, 250], [9, 7, 5, 3, 1]))
            p.reasons.append(f"Debt is {de / 100:.2f}x shareholders' equity")
    cr = _num(r.profile.get("currentRatio"))
    if cr is not None:
        scores.append(_band(cr, [1.0, 1.5], [3, 6, 9]))
        p.reasons.append(f"Current ratio {cr:.2f} (short-term assets vs bills due)")
    fcf = _num(r.profile.get("freeCashflow"))
    if fcf is not None:
        scores.append(8 if fcf > 0 else 2)
        p.reasons.append("Generates free cash flow" if fcf > 0 else "Burning cash (negative free cash flow)")
    p.score = sum(scores) / len(scores) if scores else None
    return p


def news_risk(r) -> Pillar:
    p = Pillar("News & risk", "Any warning signs or wild swings? (higher = calmer)")
    score = 10.0
    now = r.history.index[-1]
    recent = [i for i in r.timeline if i.when >= now - pd.Timedelta(days=90)]
    flags = [i for i in recent if i.red_flag]
    if flags:
        score -= min(6, 3 * len(flags))
        p.reasons.append("1 red flag in the last 90 days" if len(flags) == 1
                         else f"{len(flags)} red flags in the last 90 days")
    else:
        p.reasons.append("No red flags in the last 90 days")
    news = [i for i in recent if i.kind == "news" and i.when >= now - pd.Timedelta(days=30)]
    if news:
        balance = sum(i.sentiment for i in news) / len(news)
        score += 1 if balance > 0.2 else -1 if balance < -0.2 else 0
        tone = "mostly positive" if balance > 0.2 else "mostly negative" if balance < -0.2 else "mixed"
        p.reasons.append(f"Last month's headlines are {tone}")
    vol = r.risk.get("volatility")
    if vol is not None and pd.notna(vol):
        score -= 3 if vol > 0.6 else 2 if vol > 0.4 else 0
        p.reasons.append(f"Volatility {vol:.0%} a year")
    dd = r.risk.get("max_drawdown")
    if dd is not None and pd.notna(dd) and dd < -0.3:
        score -= 1
        p.reasons.append(f"Fell {dd:.0%} from a peak in the last year")
    p.score = _clamp(score)
    return p


def evaluate(r) -> list[Pillar]:
    return [trend(r), growth(r), profitability(r), valuation(r), health(r), news_risk(r)]


def overall(pillars: list[Pillar]) -> tuple[float | None, str]:
    scores = [p.score for p in pillars if p.score is not None]
    if not scores:
        return None, "Not enough data"
    avg = sum(scores) / len(scores)
    return avg, "Strong" if avg >= 7 else "Mixed" if avg >= 5 else "Weak"

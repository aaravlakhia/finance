"""What the news means and how much this kind of news has moved this stock before."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .classify import RED_FLAG
from .models import Item

# Display order: warnings first, then the topics investors usually care most about.
TOPICS = [RED_FLAG, "earnings", "meeting", "dividend/buyback", "management", "deal", "analyst", "other"]
# When a headline has several tags, the first match here decides its group, so
# "board meeting to approve results" lands under meetings.
PRIORITY = [RED_FLAG, "meeting", "earnings", "dividend/buyback", "management", "deal", "analyst"]
TITLES = {
    RED_FLAG: "Legal issues & red flags", "earnings": "Results & revenue", "meeting": "Meetings & AGMs",
    "dividend/buyback": "Dividends & buybacks", "management": "Management changes",
    "deal": "Deals, orders & partnerships", "analyst": "Analyst views", "other": "Other news",
}
SHORT = {RED_FLAG: "Red flags", "earnings": "Results", "meeting": "Meetings", "dividend/buyback": "Dividends",
         "management": "Management", "deal": "Deals", "analyst": "Analysts", "other": "Other"}
ICONS = {RED_FLAG: "⚠️", "earnings": "📊", "meeting": "🏛️", "dividend/buyback": "💸", "management": "👔",
         "deal": "🤝", "analyst": "🔭", "other": "🗞️"}

# Plain-English meaning of each kind of news, by tone (+1 good, -1 bad, 0 unclear).
EXPLAIN = {
    RED_FLAG: {
        0: "Investigations, lawsuits, penalties or fraud allegations create uncertainty. The damage depends on "
           "how big the possible fine or loss is compared with the company, and whether management's "
           "credibility is hit. Prices often fall first and recover only if the issue turns out small.",
    },
    "earnings": {
        1: "Good results usually lift the price, especially when revenue (not just cost cuts) drives profit "
           "and the company raises its outlook. Markets react to results versus expectations, so even good "
           "numbers can disappoint if investors hoped for more.",
        -1: "Weak results, falling revenue or a profit miss usually push the price down, and more sharply if "
            "the company also lowers its outlook. One bad quarter matters less than a trend of them.",
        0: "Results news. The price reaction depends on how revenue, profit and guidance compare with what "
           "investors expected, not just on whether profit went up.",
    },
    "meeting": {
        0: "Board meetings and AGMs are where results, dividends, buybacks, fund-raising and strategy are "
           "approved or announced. The meeting itself rarely moves the price; what gets decided does, so "
           "check the agenda and the outcome announcement.",
    },
    "dividend/buyback": {
        1: "Dividends and buybacks return cash to shareholders and signal confidence. Buybacks reduce the "
           "share count, which can support the price. On the ex-dividend date the price usually drops by "
           "about the dividend amount; that drop is not a loss.",
        -1: "A cut or cancelled dividend or buyback often signals cash pressure and can weigh on the price.",
        0: "Dividend or buyback news. It returns cash to shareholders; on the ex-dividend date the price "
           "normally drops by roughly the dividend paid.",
    },
    "management": {
        1: "A well-regarded new leader can lift confidence, especially after a weak period.",
        -1: "A sudden exit of a CEO or CFO creates uncertainty and can hit the price, particularly if no "
            "reason or successor is given.",
        0: "Leadership change. Planned successions rarely matter much; surprise departures matter more.",
    },
    "deal": {
        1: "New orders, contracts and partnerships add future revenue. Acquisitions can create value, but "
           "the buyer's shares sometimes dip if the price paid looks high or the deal adds debt.",
        -1: "Lost contracts or a troubled deal can reduce expected revenue and weigh on the price.",
        0: "Deal or partnership news. What matters is its size compared with the company's revenue and "
           "what it costs.",
    },
    "analyst": {
        1: "Upgrades and higher price targets often move the price for a day or two, especially from widely "
           "followed brokers. They are opinions, not facts.",
        -1: "Downgrades and lower targets often push the price down for a day or two. Check the reason given.",
        0: "Analyst opinion. Useful for seeing what professionals expect, but analysts are often wrong.",
    },
    "other": {
        1: "Generally positive news for the business.",
        -1: "Generally negative news for the business.",
        0: "General company news.",
    },
}

# Fallback strength when this stock has too little history for a topic.
DEFAULT_STRENGTH = {RED_FLAG: "High", "earnings": "High", "deal": "Medium", "management": "Medium",
                    "analyst": "Medium", "meeting": "Low", "dividend/buyback": "Low", "other": "Low"}


def topic_of(item: Item) -> str:
    for t in PRIORITY:
        if t in item.tags:
            return t
    return "other"


def meaning(item: Item) -> str:
    texts = EXPLAIN[topic_of(item)]
    tone = -1 if item.red_flag else item.sentiment
    return texts.get(tone, texts[0])


def explain_group(topic: str, items: list[Item]) -> list[tuple[str, str]]:
    """What a topic means, once per section: the general idea plus good/bad cases that appear."""
    texts = EXPLAIN[topic]
    tones = {(-1 if i.red_flag else i.sentiment) for i in items}
    out = [("", texts[0])] if 0 in texts else []
    if 1 in tones and 1 in texts:
        out.append(("When it's good", texts[1]))
    if -1 in tones and -1 in texts:
        out.append(("When it's bad", texts[-1]))
    return out


def headline(item: Item) -> str:
    """Exchange filings often have generic subjects ("Outcome of Board Meeting"), so add the detail."""
    if item.kind == "filing" and item.detail and item.detail not in item.title:
        text = f"{item.title}: {item.detail}"
        return text if len(text) <= 160 else text[:157] + "..."
    return item.title


def typical_move(prices: pd.DataFrame) -> float:
    """Median size of a daily move: the yardstick for 'big' or 'small'."""
    r = prices["Close"].pct_change().abs().dropna()
    return float(r.median()) if len(r) else np.nan


@dataclass
class TopicStats:
    topic: str
    days: int            # distinct trading days with this kind of item
    avg_move: float      # average % move on those days
    avg_size: float      # average absolute move
    up_share: float      # share of those days that closed higher
    vs_normal: float     # avg_size / typical daily move


def history(items: list[Item], prices: pd.DataFrame) -> dict[str, TopicStats]:
    """How each topic has moved this stock on the first trading day it could affect."""
    typical = typical_move(prices)
    by_topic: dict[str, dict] = {}
    for item in items:
        if item.reaction is None or item.reaction_day is None:
            continue
        # Several headlines about the same day count once.
        by_topic.setdefault(topic_of(item), {})[item.reaction_day] = item.reaction
    out = {}
    for topic, days in by_topic.items():
        moves = np.array(list(days.values()))
        size = float(np.abs(moves).mean())
        out[topic] = TopicStats(topic, len(moves), float(moves.mean()), size, float((moves > 0).mean()),
                                size / typical if typical else np.nan)
    return out


def rating(item: Item, stats: dict[str, TopicStats]) -> tuple[str, str]:
    """(direction, strength) such as ('Positive', 'High')."""
    tone = -1 if item.red_flag else item.sentiment
    direction = {1: "Positive", -1: "Negative", 0: "Unclear"}[tone]
    topic = topic_of(item)
    s = stats.get(topic)
    if s and s.days >= 3 and pd.notna(s.vs_normal):
        strength = "High" if s.vs_normal >= 2 else "Medium" if s.vs_normal >= 1.3 else "Low"
    else:
        strength = DEFAULT_STRENGTH[topic]
    return direction, strength


def grouped(items: list[Item], kinds=("news", "filing")) -> dict[str, list[Item]]:
    """Items by topic in display order, newest first within each topic."""
    groups = {t: [] for t in TOPICS}
    for item in items:
        if item.kind in kinds:
            groups[topic_of(item)].append(item)
    return {t: sorted(v, key=lambda i: i.when, reverse=True) for t, v in groups.items() if v}


def pulse(items: list[Item], weeks: int = 12, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Headline counts per week by tone (Positive / Neutral / Negative), oldest week first."""
    news = [i for i in items if i.kind == "news"]
    now = now or pd.Timestamp.now(tz="UTC")
    start = (now - pd.Timedelta(weeks=weeks)).tz_convert("UTC").normalize()
    rows = []
    for i in news:
        when = i.when.tz_convert("UTC")
        if when >= start:
            tone = "Negative" if i.red_flag or i.sentiment < 0 else "Positive" if i.sentiment > 0 else "Neutral"
            rows.append({"week": when.tz_localize(None).to_period("W-SUN").start_time, "tone": tone})
    frame = pd.DataFrame(rows, columns=["week", "tone"])
    table = frame.pivot_table(index="week", columns="tone", aggfunc="size", fill_value=0)
    all_weeks = pd.period_range(start.tz_localize(None), now.tz_convert("UTC").tz_localize(None), freq="W-SUN")
    table = table.reindex([p.start_time for p in all_weeks], fill_value=0)
    for col in ("Positive", "Neutral", "Negative"):
        if col not in table:
            table[col] = 0
    return table[["Positive", "Neutral", "Negative"]].astype(int)

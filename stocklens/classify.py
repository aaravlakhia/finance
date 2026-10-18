"""Tag headlines by topic and tone using keyword rules.

Deliberately simple (no ML model, no downloads) so it runs anywhere. It will
sometimes be wrong - e.g. "lawsuit dismissed" is still tagged legal - so treat
tags as a filter that points you at headlines worth reading, not a verdict.
"""

import re

RED_FLAG = "scandal/legal"

# Patterns are regex fragments matched at a word start, case-insensitive.
CATEGORIES: dict[str, list[str]] = {
    RED_FLAG: [
        r"fraud\w*", r"scam\w*", r"scandal\w*", r"probe[sd]?\b", r"investigat\w*",
        r"law ?suits?", r"sue[sd]?\b", r"class[- ]action", r"indict\w*", r"charged\b",
        r"(?:criminal|fraud) charges", r"penalt\w*", r"fined\b", r"show[- ]cause",
        r"raid\w*", r"whistle-?blower\w*", r"irregularit\w*", r"restat(?:e|es|ed|ement)\b",
        r"insider trading", r"brib\w*", r"money laundering", r"embezzl\w*",
        r"default(?:s|ed)?\b", r"bankrupt\w*", r"insolven\w*", r"nclt\b",
        r"short[- ]sell\w*", r"hindenburg", r"alleg\w*", r"misconduct", r"subpoena\w*",
        r"antitrust", r"data breach", r"cyber ?attack\w*", r"hack(?:ed|ers?)\b",
        r"recall\w*", r"delist\w*", r"going concern", r"cbi\b", r"crackdown",
    ],
    "earnings": [
        r"results?\b", r"earnings", r"quarterly", r"q[1-4]\b", r"(?:net )?profits?\b",
        r"revenues?\b", r"net income", r"eps\b", r"guidance", r"outlook", r"sales\b",
        r"margins?\b", r"fy ?\d{2,4}\b", r"forecast\w*",
    ],
    "meeting": [
        r"agm\b", r"annual general meeting", r"egm\b", r"extraordinary general meeting",
        r"(?:share|stock)holders?'? meeting", r"annual meeting", r"board meeting",
        r"proxy\b", r"shareholder vote", r"postal ballot", r"investor day",
        r"analysts? meet\w*", r"earnings call", r"con(?:ference)? call",
    ],
    "dividend/buyback": [
        r"dividends?\b", r"buy-?backs?\b", r"(?:share|stock) repurchase\w*",
        r"(?:stock|share) split\w*", r"bonus (?:issue|shares?)", r"rights issue",
        r"record date", r"ex-dividend",
    ],
    "management": [
        r"ceo\b", r"cfo\b", r"coo\b", r"chairman\b", r"chairperson\b", r"managing director",
        r"resign\w*", r"steps? down", r"appoint\w*", r"names? new", r"succession",
        r"successor", r"board of directors",
    ],
    "deal": [
        r"acqui\w*", r"merg(?:e|er|ers|es|ed|ing)\b", r"takeover", r"stake\b", r"deals?\b",
        r"partner\w*", r"joint venture", r"contracts?\b", r"orders? win", r"bags?\b",
        r"tie-?up", r"buyout",
    ],
    "analyst": [
        r"upgrad\w*", r"downgrad\w*", r"price target", r"target price", r"ratings?\b",
        r"outperform\w*", r"underperform\w*", r"overweight", r"underweight",
        r"analysts?\b", r"brokerages?\b", r"initiat\w* coverage",
    ],
}

POSITIVE = [
    r"beat(?:s|ing)?\b", r"surg\w*", r"soar\w*", r"jump\w*", r"rall(?:y|ies|ied)\b",
    r"gains?\b", r"gained", r"ris(?:e|es|ing)\b", r"rose\b", r"record(?! date)",
    r"upgrad\w*", r"strong\w*", r"growth", r"grow(?:s|n|ing)?\b", r"outperform\w*",
    r"wins?\b", r"won\b", r"bags?\b", r"approv\w*", r"expan(?:d|ds|ded|ding|sion)\b", r"boost\w*",
    r"raises? (?:guidance|outlook|forecast|dividend)", r"bullish", r"exceed\w*",
    r"top(?:s|ped) (?:estimates|expectations)", r"rebound\w*", r"recover\w*",
    r"climb\w*", r"higher\b", r"buy rating",
]

NEGATIVE = [
    r"miss(?:es|ed)?\b", r"plung\w*", r"slump\w*", r"fall(?:s|ing)?\b", r"fell\b",
    r"drop\w*", r"declin\w*", r"slid(?:e|es|ing)?\b", r"tumbl\w*", r"crash\w*",
    r"sink\w*", r"sank\b", r"loss(?:es)?\b", r"weak\w*", r"cuts?\b", r"cutting",
    r"downgrad\w*", r"lay-?offs?\b", r"job cuts", r"warn\w*", r"bearish", r"concern\w*",
    r"slash\w*", r"underperform\w*", r"sell rating", r"halt\w*", r"delay\w*",
    r"lowers? (?:guidance|outlook|forecast)", r"worst\b", r"sell-?off\b", r"tank(?:s|ed)\b",
    r"disappoint\w*", r"pressure\b", r"lower\b",
]


def _compile(patterns: list[str]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(patterns) + ")", re.IGNORECASE)


_CATEGORY_RE = {name: _compile(p) for name, p in CATEGORIES.items()}
_POSITIVE_RE = _compile(POSITIVE)
_NEGATIVE_RE = _compile(NEGATIVE)


def classify(text: str) -> tuple[list[str], int, bool]:
    """Return (tags, sentiment, red_flag) for a headline or filing description.

    sentiment is -1, 0 or +1. A red flag pulls the tone one step negative.
    """
    tags = [name for name, rx in _CATEGORY_RE.items() if rx.search(text)]
    red_flag = RED_FLAG in tags
    score = len(_POSITIVE_RE.findall(text)) - len(_NEGATIVE_RE.findall(text))
    if red_flag:
        score -= 1
    sentiment = (score > 0) - (score < 0)
    return tags, sentiment, red_flag

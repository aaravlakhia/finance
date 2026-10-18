"""Number formatting for both markets (US: K/M/B/T, India: Cr / lakh Cr)."""

import math

from .symbols import Market


def _missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def money(value, market: Market) -> str:
    """Compact amount, e.g. $2.31T or ₹1,234 Cr."""
    if _missing(value):
        return "-"
    sign = "-" if value < 0 else ""
    v = abs(float(value))
    cs = market.currency_sign
    if market.code == "IN":
        if v >= 1e12:
            return f"{sign}{cs}{v / 1e12:,.2f} lakh Cr"
        if v >= 1e9:
            return f"{sign}{cs}{v / 1e7:,.0f} Cr"
        if v >= 1e7:
            return f"{sign}{cs}{v / 1e7:,.1f} Cr"
        return f"{sign}{cs}{v:,.0f}"
    for div, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if v >= div:
            return f"{sign}{cs}{v / div:,.2f}{suffix}"
    return f"{sign}{cs}{v:,.0f}"


def price(value, market: Market) -> str:
    if _missing(value):
        return "-"
    return f"{market.currency_sign}{value:,.2f}"


def pct(value, signed: bool = True) -> str:
    """0.0123 -> '+1.23%'."""
    if _missing(value):
        return "-"
    return f"{value * 100:+.2f}%" if signed else f"{value * 100:.2f}%"


def number(value, digits: int = 2) -> str:
    if _missing(value):
        return "-"
    return f"{value:,.{digits}f}"

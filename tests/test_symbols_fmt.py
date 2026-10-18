import pytest

from stocklens import fmt
from stocklens.symbols import INDIA, US, resolve


@pytest.mark.parametrize("text,market,yahoo,exchange", [
    ("aapl", None, "AAPL", "US"),
    ("INFY.NS", None, "INFY.NS", "NSE"),
    ("reliance.bo", None, "RELIANCE.BO", "BSE"),
    ("TCS", "in", "TCS.NS", "NSE"),
    ("TCS", "nse", "TCS.NS", "NSE"),
    ("SBIN", "bse", "SBIN.BO", "BSE"),
    ("NSE:HDFCBANK", None, "HDFCBANK.NS", "NSE"),
    ("BSE:500325", None, "500325.BO", "BSE"),
    ("500325", None, "500325.BO", "BSE"),
    ("BRK.B", None, "BRK-B", "US"),
    ("M&M", "in", "M&M.NS", "NSE"),
])
def test_resolve(text, market, yahoo, exchange):
    t = resolve(text, market)
    assert (t.yahoo, t.exchange) == (yahoo, exchange)
    assert t.market is (US if exchange == "US" else INDIA)


def test_resolve_empty():
    with pytest.raises(ValueError):
        resolve("  ")


def test_money_formats():
    assert fmt.money(2.31e12, US) == "$2.31T"
    assert fmt.money(-4.5e8, US) == "-$450.00M"
    assert fmt.money(6.32e12, INDIA) == "₹6.32 lakh Cr"
    assert fmt.money(4.1e10, INDIA) == "₹4,100 Cr"
    assert fmt.money(2.5e7, INDIA) == "₹2.5 Cr"
    assert fmt.money(None, US) == "-"
    assert fmt.money(float("nan"), US) == "-"


def test_pct_and_price():
    assert fmt.pct(0.0123) == "+1.23%"
    assert fmt.pct(-0.05, signed=False) == "-5.00%"
    assert fmt.price(1523.4, INDIA) == "₹1,523.40"

import pytest

from stocklens.classify import RED_FLAG, classify


@pytest.mark.parametrize("headline,tag", [
    ("SEBI issues show-cause notice to Acme Industries", RED_FLAG),
    ("SEC opens probe into accounting at XYZ Corp", RED_FLAG),
    ("Shareholders file class action lawsuit against company", RED_FLAG),
    ("Acme Q2 results: net profit rises 5% YoY", "earnings"),
    ("Acme AGM 2026: key announcements for shareholders", "meeting"),
    ("Board meeting on Oct 20 to consider interim dividend", "meeting"),
    ("Acme announces Rs 17,000 crore buyback", "dividend/buyback"),
    ("CEO steps down after 10 years", "management"),
    ("Company to acquire rival in $2 billion deal", "deal"),
    ("Morgan Stanley upgrades stock, raises price target", "analyst"),
])
def test_tags(headline, tag):
    tags, _, _ = classify(headline)
    assert tag in tags


def test_sentiment():
    assert classify("Acme shares surge after record sales beat estimates")[1] == 1
    assert classify("Stock plunges as profit misses estimates")[1] == -1
    assert classify("Company holds annual meeting in New York")[1] == 0


def test_red_flag_is_negative():
    tags, sentiment, red = classify("Fraud allegations hit Acme subsidiary")
    assert red and sentiment == -1


def test_record_date_not_positive():
    assert classify("Board fixes record date for dividend")[1] == 0


def test_no_false_red_flag():
    assert classify("Acme wins large deal from European bank")[2] is False

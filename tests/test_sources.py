"""Parsing of news feeds and filings, using small sample responses (no network)."""

import pandas as pd

from stocklens import filings, fundamentals, marketdata, news
from stocklens.symbols import resolve

GOOGLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Google News</title>
<item>
  <title>Acme Corp faces SEC probe over revenue accounting - Example Wire</title>
  <link>https://news.google.com/rss/articles/abc</link>
  <pubDate>Tue, 14 Oct 2026 21:05:00 GMT</pubDate>
  <source url="https://example.com">Example Wire</source>
</item>
<item>
  <title>Acme Corp quarterly profit beats estimates - Daily Ledger</title>
  <link>https://news.google.com/rss/articles/def</link>
  <pubDate>Mon, 13 Oct 2026 12:00:00 GMT</pubDate>
  <source url="https://example.org">Daily Ledger</source>
</item>
<item><title>Broken item without a date</title></item>
</channel></rss>"""


def test_parse_google_rss():
    items = news.parse_google_rss(GOOGLE_RSS)
    assert len(items) == 2
    probe, beat = items
    assert probe.title == "Acme Corp faces SEC probe over revenue accounting"
    assert probe.source == "Example Wire"
    assert probe.red_flag and probe.sentiment == -1
    assert probe.when == pd.Timestamp("2026-10-14 21:05", tz="UTC")
    assert beat.sentiment == 1 and "earnings" in beat.tags


def test_parse_yahoo_news_both_formats():
    raw = [
        {"id": "1", "content": {"title": "Acme launches new product", "pubDate": "2026-10-10T14:00:00Z",
                                "provider": {"displayName": "Yahoo Finance"},
                                "canonicalUrl": {"url": "https://finance.yahoo.com/a"}, "summary": "s"}},
        {"title": "Acme shares slump on weak guidance", "publisher": "Wire",
         "link": "https://x", "providerPublishTime": 1760000000},
        {"content": {"title": None}},
    ]
    items = marketdata.parse_yahoo_news(raw)
    assert [i.source for i in items] == ["Yahoo Finance", "Wire"]
    assert items[0].url == "https://finance.yahoo.com/a"
    assert items[1].sentiment == -1
    assert all(i.when.tzinfo is not None for i in items)


def test_merge_dedupes_and_keeps_red_flags():
    probe, beat = news.parse_google_rss(GOOGLE_RSS)
    assert len(news.merge([[probe, beat], [probe, beat]], limit=5)) == 2
    # Make the red flag the older item: it survives even though it is past the limit.
    probe.when -= pd.Timedelta(days=30)
    merged = news.merge([[probe, beat]], limit=1)
    assert merged == [beat, probe]


def test_is_relevant():
    t = resolve("TCS.NS")
    assert news.is_relevant("Tata Consultancy wins deal", "Tata Consultancy Services", t)
    assert news.is_relevant("TCS shares rise 2%", "Tata Consultancy Services", t)
    assert not news.is_relevant("Sensex closes higher", "Tata Consultancy Services", t)
    a = resolve("AAPL")
    assert news.is_relevant("Apple unveils new iPhone", "Apple", a)
    assert not news.is_relevant("Pineapple prices jump", "Apple", a)


def test_queries_by_market():
    assert news.queries("Infosys", resolve("INFY.NS"))[0] == '"Infosys" share price'
    assert news.queries("Apple", resolve("AAPL"))[0] == '"Apple" stock'


def test_search_name():
    assert marketdata.search_name("Apple Inc.") == "Apple"
    assert marketdata.search_name("Infosys Limited") == "Infosys"
    assert marketdata.search_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert marketdata.search_name("The Goldman Sachs Group, Inc.") == "Goldman Sachs"
    assert marketdata.search_name("Tata Consultancy Services Limited") == "Tata Consultancy Services"


SEC_SUBMISSIONS = {
    "cik": "0000320193",
    "filings": {"recent": {
        "accessionNumber": ["0000320193-26-000101", "0000320193-26-000090", "0000320193-26-000080",
                            "0000320193-26-000070", "0000320193-26-000010"],
        "filingDate": ["2026-10-01", "2026-08-01", "2026-07-30", "2026-07-15", "2025-01-10"],
        "acceptanceDateTime": ["2026-10-01T08:00:00.000Z", "2026-08-01T16:30:12.000Z",
                               "2026-07-30T18:01:00.000Z", "2026-07-15T09:00:00.000Z",
                               "2025-01-10T09:00:00.000Z"],
        "form": ["8-K", "8-K", "10-Q", "4", "DEF 14A"],
        "items": ["4.02,9.01", "2.02,9.01", "", "", ""],
        "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.xml", "e.htm"],
    }},
}


def test_parse_sec_submissions():
    since = pd.Timestamp("2026-01-01", tz="America/New_York")
    items = filings.parse_sec_submissions(SEC_SUBMISSIONS, since)
    assert [i.source for i in items] == ["SEC 8-K", "SEC 8-K", "SEC 10-Q"]  # Form 4 skipped, DEF 14A too old
    restatement, results, quarterly = items
    assert restatement.red_flag and "can no longer be relied on" in restatement.title
    assert "earnings" in results.tags and not results.red_flag
    assert results.when == pd.Timestamp("2026-08-01 16:30:12", tz="America/New_York")
    assert results.url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000090/b.htm"


def test_parse_sec_proxy_is_meeting():
    items = filings.parse_sec_submissions(SEC_SUBMISSIONS, pd.Timestamp("2024-01-01", tz="UTC"))
    proxy = [i for i in items if i.source == "SEC DEF 14A"][0]
    assert "meeting" in proxy.tags


NSE_ANNOUNCEMENTS = [
    {"symbol": "ACME", "desc": "Outcome of Board Meeting", "sort_date": "2026-10-16 17:45:00",
     "attchmntText": "Board approved financial results for the quarter and declared interim dividend",
     "attchmntFile": "https://nsearchives.nseindia.com/corporate/acme.pdf"},
    {"symbol": "ACME", "desc": "Action(s) initiated or orders passed",
     "an_dt": "02-Oct-2026 11:00:00",
     "attchmntText": "SEBI has imposed a penalty on the company", "attchmntFile": ""},
    {"symbol": "ACME", "desc": "Shareholders meeting", "sort_date": "2020-01-01 10:00:00",
     "attchmntText": "Old AGM notice"},
    {"symbol": "ACME", "desc": "Row with no date", "attchmntText": "skipped"},
]


def test_parse_nse_announcements():
    since = pd.Timestamp("2026-01-01", tz="Asia/Kolkata")
    items = filings.parse_nse_announcements(NSE_ANNOUNCEMENTS, since)
    assert len(items) == 2
    board, penalty = items
    assert {"meeting", "earnings", "dividend/buyback"} <= set(board.tags)
    assert board.when == pd.Timestamp("2026-10-16 17:45", tz="Asia/Kolkata")
    assert penalty.red_flag
    # The API sometimes wraps rows in {"data": [...]}.
    assert len(filings.parse_nse_announcements({"data": NSE_ANNOUNCEMENTS}, since)) == 2


def test_summarize_income_statement():
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"])
    stmt = pd.DataFrame(
        [[130.0, 120, 110, 100, None], [15.0, 12, 11, 10, None], [1.5, 1.2, 1.1, 1.0, None]],
        index=["Total Revenue", "Net Income", "Diluted EPS"], columns=cols)
    out = fundamentals.summarize(stmt)
    assert list(out.index) == sorted(cols[:4])  # oldest first, empty padding column dropped
    assert out["Revenue"].iloc[-1] == 130
    assert abs(out["Net margin"].iloc[-1] - 15 / 130) < 1e-9
    assert abs(out["Revenue growth"].iloc[-1] - (130 / 120 - 1)) < 1e-9
    assert fundamentals.summarize(pd.DataFrame()).empty

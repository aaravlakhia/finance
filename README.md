# stocklens

A lightweight Python tool for researching **US and Indian stocks**. Type a symbol and
it pulls together, in one place:

- **Price trend:** 50/200-day moving averages, RSI, MACD, Bollinger bands, volume,
  performance and volatility, turned into plain-English signals.
- **Financials:** quarterly and annual revenue, net profit, margin, EPS and growth.
- **Events:** upcoming earnings and dividend dates, past earnings beats/misses,
  dividends and splits.
- **Filings:** SEC filings for US companies (earnings releases, shareholder
  meetings, management changes, restatements, late filings) and NSE corporate
  announcements for Indian companies (board meetings, AGMs, results, regulatory actions).
- **News:** recent headlines from Google News and Yahoo Finance, tagged by topic
  (scandal/legal, earnings, meeting, dividend, management, deal, analyst) and tone.
- **The link between them:** every headline, filing and event is matched to the
  first trading day it could affect, along with that day's price move. The
  biggest moves in the period are listed next to the news that may explain them.
- **Briefing:** everything above condensed into a few plain-English sentences.
- **Outlook (prediction lab):** nobody can predict exact prices, so instead you get:
  - the price range the stock is likely (50%) and very likely (90%) to be in after
    1, 3 and 6 months, based on how much it usually moves (shaded on the chart);
  - what happened after past days that looked like today (same trend and momentum);
  - an honest **track record**: how often that method would have called the
    direction right on this stock, compared with always guessing "up";
  - a backtest of a simple trend rule against buy-and-hold.
- **Investment checklist:** trend, growth, profitability, valuation, financial
  health and news risk, each scored out of 10 with the reasons shown.
- **Vs the market:** the stock against the S&P 500 or NIFTY 50, plus beta.
- **Analyst targets and ownership:** low/average/high targets and consensus, and
  how much insiders and institutions own.
- **Invest calculator:** what a one-time investment or a monthly SIP would be
  worth today (with XIRR).
- **Watchlist:** cards with mini charts for up to 8 stocks at the top of the dashboard.

It runs on an ordinary laptop. There's no database, no API keys and no machine-learning
model to download. The core needs only `yfinance`, `pandas` and `requests`.

> For research and learning only, not financial advice. Signals describe past price
> behaviour; they do not predict future prices.

## Easiest: run it from Spyder (no terminal)

If you use Anaconda/Spyder (or IDLE, VS Code, PyCharm):

1. Download this branch as a ZIP from GitHub (green **Code** button, then
   **Download ZIP**) and unzip it.
2. In Spyder, use **File > Open** to open `run.py` from the unzipped folder.
3. Press **Run** (F5).
4. When the console asks *"Which stock?"*, type a symbol (e.g. `TSLA` or `TCS.NS`,
   or several: `AAPL, TCS.NS`) and press Enter.

The first run installs the missing packages automatically. The dashboard then opens
in your browser on the stock you typed. Switch stocks from the dropdown in its sidebar
and add your favourites to the watchlist. To stop it, click the red Stop square above
the console. For a text report in the console instead, set `MODE = "report"` in `run.py`.

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/aaravlakhia/finance.git
cd finance
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt              # command-line tool only
pip install -r requirements-dashboard.txt    # + browser dashboard (Streamlit, Plotly)
```

## Use it

### Command line

```bash
python -m stocklens AAPL                 # US stock
python -m stocklens INFY.NS              # Indian stock on NSE
python -m stocklens RELIANCE.BO          # Indian stock on BSE
python -m stocklens TCS -m in            # bare symbol, treat as India (NSE)
python -m stocklens AAPL -p 6mo -n 30    # 6-month window, show 30 timeline items
python -m stocklens AAPL MSFT INFY.NS    # watchlist: one line per stock
python -m stocklens AAPL --no-news       # faster, skip news
```

What the sections look like (illustrative, trimmed):

```
TREND  Bullish leaning (score +2)
  + Uptrend: price is above its 50-day and 200-day averages
  · RSI 51: neutral
  + Revenue grew in each of the last 3 quarterly periods

FINANCIALS (quarterly)
  Quarter       Revenue     Net profit   Margin    EPS   Rev chg
  ...

RED FLAGS (1)
! 2026-07-01 [scandal/legal] Regulator opens probe into ... (Wire)  -> -4.10% (big move)

BIGGEST MOVES & POSSIBLE CAUSES
  2026-07-01    -4.10%
      <- Regulator opens probe into ... (Wire)

TIMELINE (news, filings, events)
+ 2026-08-20 [earnings] Q1 net profit rises 9%, beats estimates (Wire)  -> +2.30%
```

`+` positive, `-` negative, `·` neutral, `!` red flag, `->` the price move on the
first trading day the item could affect.

### Dashboard

```bash
streamlit run app.py
```

This opens in your browser. You get an interactive price chart with news and filing
markers on it (hover to read the headlines), signals, red flags, upcoming events, the
biggest moves with possible causes, revenue/profit charts, and a filterable timeline.
It follows your light/dark theme.

## Symbols

| Market | How to type it | Examples |
|---|---|---|
| US (NYSE/NASDAQ) | plain ticker | `AAPL`, `MSFT`, `BRK.B` |
| India, NSE | `.NS` suffix, `NSE:` prefix, or `-m in` | `INFY.NS`, `NSE:TCS`, `HDFCBANK -m in` |
| India, BSE | `.BO` suffix, `BSE:` prefix, `-m bse`, or 6-digit code | `RELIANCE.BO`, `500325` |

Prices and amounts are shown in the stock's own currency. Indian amounts are shown in
crore (Cr) and lakh crore.

## Where the data comes from

| Data | Source | Notes |
|---|---|---|
| Prices, profile, financials, earnings dates | Yahoo Finance via [`yfinance`](https://github.com/ranaroussi/yfinance) | Free, unofficial, usually ~15 min delayed |
| News | Google News RSS + Yahoo Finance | Free, no key. Three searches per company: general, possible scandals, meetings/results |
| US filings | [SEC EDGAR](https://www.sec.gov/edgar) | Official and free |
| Indian filings | NSE corporate announcements | Best effort: NSE sometimes blocks scripted access, in which case this section is skipped with a note |

When a source fails, the report still prints. It lists what couldn't be loaded under
"Notes" (CLI) or in a yellow box (dashboard).

### Optional settings

| Environment variable | Purpose |
|---|---|
| `STOCKLENS_SEC_USER_AGENT` | The SEC asks tools to identify themselves. Set it to `"your-name your-email@example.com"` |
| `STOCKLENS_CACHE` | Where the SEC ticker list is cached (default `~/.cache/stocklens`) |

## How it decides things

- **Topic tags and tone** come from keyword rules in `stocklens/classify.py`. They
  are quick and work offline, but they're not perfect. For example, "lawsuit
  dismissed" is still tagged legal. Use them to find headlines worth reading, not as
  a verdict. You can add your own keywords there.
- **Red flags** are headlines or filings that mention fraud, probes, lawsuits,
  penalties, raids, defaults, restatements and so on. On the SEC side they include
  bankruptcy, auditor changes, financial statements that can no longer be relied
  on, delisting notices and late-filing notices.
- **Reaction day:** news published after the market closes (4:00 pm New York,
  3:30 pm India) or on a weekend is matched to the next trading day.
- **Big move:** a daily change larger than two standard deviations of the stock's
  daily moves over the period.
- **Trend score:** each bullish signal adds 1 and each bearish signal subtracts 1.
  A score of +2 or more reads "Bullish leaning", -2 or less reads "Bearish leaning".

## Project layout

```
app.py                  Streamlit dashboard (the all-in-one space)
run.py                  one-click launcher for Spyder / IDLE / VS Code
stocklens/
  cli.py                command-line interface
  report.py             fetches everything and builds one Report
  marketdata.py         prices, profile, calendar, Yahoo news (yfinance)
  fundamentals.py       revenue / profit / margin / EPS tables
  indicators.py         SMA, EMA, RSI, MACD, Bollinger (pure pandas)
  signals.py            plain-language trend & fundamentals signals
  news.py               Google News RSS search, de-duplication, relevance filter
  filings.py            SEC EDGAR and NSE announcements
  classify.py           topic / tone / red-flag keyword rules
  timeline.py           links items to price moves
  forecast.py           likely ranges, "days like today", track record, backtest
  scorecard.py          the six-pillar investment checklist
  briefing.py           the plain-English summary
  invest.py             lump-sum and SIP calculators (with XIRR)
  charts.py             Plotly charts for the dashboard
tests/                  offline tests (no network needed)
```

## Tests

```bash
pip install pytest
python -m pytest
```

The tests use synthetic prices and sample API responses, so they run offline.

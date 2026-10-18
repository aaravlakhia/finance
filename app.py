"""Dashboard: streamlit run app.py"""

import pandas as pd
import streamlit as st

from stocklens import DISCLAIMER, fmt
from stocklens.charts import financials_chart, price_chart
from stocklens.report import PERIODS, NoPriceData, build

st.set_page_config(page_title="stocklens", page_icon="📈", layout="wide")

MARKETS = {"Auto (US unless .NS/.BO)": None, "US": "us", "India - NSE": "nse", "India - BSE": "bse"}
TONE_LABEL = {1: "▲ positive", -1: "▼ negative", 0: "· neutral"}
POPULAR = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "GOOGL": "Alphabet (Google)",
    "AMZN": "Amazon", "META": "Meta", "TSLA": "Tesla",
    "RELIANCE.NS": "Reliance Industries", "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank", "INFY.NS": "Infosys", "ICICIBANK.NS": "ICICI Bank",
    "SBIN.NS": "State Bank of India", "BHARTIARTL.NS": "Bharti Airtel", "ITC.NS": "ITC",
    "LT.NS": "Larsen & Toubro", "HINDUNILVR.NS": "Hindustan Unilever",
}


@st.cache_data(ttl=900, show_spinner=False)
def load(symbol, market, period, news, filings):
    return build(symbol, market, period, include_news=news, include_filings=filings)


def md(text: str) -> str:
    """Escape text for st.markdown: '$' would start LaTeX math and brackets break links."""
    return text.replace("$", "\\$").replace("[", "\\[").replace("]", "\\]")


def theme_mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except AttributeError:
        return "light"


with st.sidebar:
    st.title("📈 stocklens")
    st.caption("Trend · financials · events · filings · news")
    # run.py opens the page as ?symbol=TCS.NS so the dashboard starts on the stock you asked for.
    start = (st.query_params.get("symbol") or "AAPL").strip().upper()
    options = list(POPULAR) if start in POPULAR else [start, *POPULAR]
    symbol = st.selectbox(
        "Stock", options, index=options.index(start), accept_new_options=True,
        format_func=lambda s: f"{s} · {POPULAR[s]}" if s in POPULAR else s,
        help="Pick one, or type any symbol and press Enter: TSLA, WIPRO.NS, RELIANCE.BO, NSE:HDFCBANK")
    market = MARKETS[st.radio("Market", list(MARKETS))]
    period = st.selectbox("Chart period", PERIODS, index=PERIODS.index("1y"))
    with st.expander("Options"):
        use_news = st.checkbox("News", True)
        use_filings = st.checkbox("SEC / NSE filings", True)
        show_bands = st.checkbox("Bollinger bands", False)
        show_macd = st.checkbox("MACD panel", False)
    st.caption(DISCLAIMER)

if not symbol or not symbol.strip():
    st.info("Pick or type a stock in the sidebar.")
    st.stop()

try:
    with st.spinner(f"Fetching {symbol.upper()}…"):
        r = load(symbol, market, period, use_news, use_filings)
except NoPriceData as exc:
    st.error(str(exc))
    st.stop()

m = r.ticker.market
p = r.profile
mode = theme_mode()

st.header(f"{r.name} ({r.ticker.yahoo})")
st.caption(" · ".join(x for x in (r.ticker.exchange, m.name, p.get("sector"), p.get("industry")) if x))

perf = r.performance
c = st.columns(3)
c[0].metric("Price", fmt.price(r.last_close, m), fmt.pct(perf["1D"]), border=True)
c[1].metric("1 month", fmt.pct(perf["1M"]), border=True)
c[2].metric("1 year", fmt.pct(perf["1Y"]), border=True)
c = st.columns(3)
c[0].metric("Market cap", fmt.money(p.get("marketCap"), m), border=True)
c[1].metric("P/E", fmt.number(p.get("trailingPE"), 1), border=True)
c[2].metric("Signals", r.verdict.split()[0], f"score {r.score:+d}", delta_color="off", border=True)

st.plotly_chart(price_chart(r.prices, r.timeline, m, mode, show_bands, show_macd),
                theme=None, config={"displaylogo": False})
st.caption("Markers sit on the first trading day each item could affect: ✕ red flag · ▲ positive · "
           "▼ negative · ● neutral/filing. Hover for headlines and the move that day.")

left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("Signals")
    for s in r.signals:
        icon = {1: "🟢", -1: "🔴", 0: "⚪"}[s.tone]
        st.markdown(f"{icon} {md(s.text)}  \n<span style='opacity:.6;font-size:.85em'>{s.group}</span>",
                    unsafe_allow_html=True)
    st.caption(md(f"52-week range {fmt.price(r.risk['low_52w'], m)} – {fmt.price(r.risk['high_52w'], m)} · "
                  f"volatility {fmt.pct(r.risk['volatility'], signed=False)}/yr · "
                  f"max drawdown (1y) {fmt.pct(r.risk['max_drawdown'])}"
                  + (f" · dividend yield {fmt.pct(r.dividend_yield, signed=False)}" if r.dividend_yield else "")))

with right:
    st.subheader(f"Red flags ({len(r.red_flags)})")
    if r.red_flags:
        for i in r.red_flags[:6]:
            day = i.when.tz_convert(m.timezone).strftime("%d %b %Y")
            move = f" · move {fmt.pct(i.reaction)}" if i.reaction is not None else ""
            st.markdown(f"⚠️ **{day}** [{md(i.title)}]({i.url}) — {md(i.source)}{move}" if i.url
                        else f"⚠️ **{day}** {md(i.title)} — {md(i.source)}{move}")
    else:
        st.success("No scandal / legal keywords in recent news and filings.")
    st.subheader("Coming up")
    if r.upcoming:
        for e in r.upcoming:
            st.markdown(f"📅 **{e.when.tz_convert(m.timezone):%d %b %Y}** {md(e.title)}"
                        + (f" ({md(e.detail)})" if e.detail else ""))
    else:
        st.caption("No upcoming earnings or dividend dates found.")

st.subheader("Biggest moves & possible causes")
for mv in r.moves:
    with st.expander(f"{mv.day:%d %b %Y}  ·  {fmt.pct(mv.change)}", expanded=False):
        if mv.causes:
            for cause in mv.causes:
                flag = "⚠️ " if cause.red_flag else ""
                st.markdown(f"- {flag}[{md(cause.title)}]({cause.url}) — {md(cause.source)}" if cause.url
                            else f"- {flag}{md(cause.title)} — {md(cause.source)}")
        else:
            st.caption("No matching news or filing found for this day.")

st.subheader("Revenue & profit")
tab_q, tab_a = st.tabs(["Quarterly", "Annual"])
for tab, df, freq in ((tab_q, r.quarterly, "quarterly"), (tab_a, r.annual, "annual")):
    with tab:
        if df.empty or "Revenue" not in df:
            st.caption("Financial statements not available for this stock.")
            continue
        st.plotly_chart(financials_chart(df, m, mode, freq), theme=None, config={"displaylogo": False})
        table = pd.DataFrame({
            "Period end": df.index.strftime("%Y-%m-%d"),
            "Revenue": [fmt.money(v, m) for v in df["Revenue"]],
            "Net profit": [fmt.money(v, m) for v in df.get("Net profit", [None] * len(df))],
            "Net margin": [fmt.pct(v, signed=False) for v in df.get("Net margin", [None] * len(df))],
            "EPS": [fmt.number(v) for v in df.get("EPS", [None] * len(df))],
            "Revenue growth": [fmt.pct(v) for v in df["Revenue growth"]],
        })
        st.dataframe(table, hide_index=True)

st.subheader("Timeline: news, filings & events")
if r.timeline:
    all_tags = sorted({t for i in r.timeline for t in i.tags})
    f1, f2, f3 = st.columns([2, 3, 1])
    kinds = f1.multiselect("Type", ["news", "filing", "event"], default=["news", "filing", "event"])
    tags = f2.multiselect("Topics", all_tags, placeholder="All topics")
    flags_only = f3.checkbox("Red flags only")
    rows = [i for i in r.timeline
            if i.kind in kinds and (not tags or set(tags) & set(i.tags)) and (i.red_flag or not flags_only)]
    st.dataframe(
        pd.DataFrame({
            "Date": [i.when.tz_convert(m.timezone).strftime("%Y-%m-%d %H:%M") if i.has_time
                     else i.when.tz_convert(m.timezone).strftime("%Y-%m-%d") for i in rows],
            "Tone": ["⚠ red flag" if i.red_flag else TONE_LABEL[i.sentiment] for i in rows],
            "Headline": [i.title for i in rows],
            "Topics": [", ".join(i.tags) for i in rows],
            "Source": [i.source for i in rows],
            "Move that day": [None if i.reaction is None else i.reaction * 100 for i in rows],
            "Link": [i.url or None for i in rows],
        }),
        hide_index=True,
        column_config={
            "Move that day": st.column_config.NumberColumn(format="%+.2f%%"),
            "Link": st.column_config.LinkColumn(display_text="open"),
            "Headline": st.column_config.TextColumn(width="large"),
        },
    )
else:
    st.caption("No news, filings or events found.")

if r.warnings:
    st.warning(md("Some data couldn't be loaded: " + "; ".join(dict.fromkeys(r.warnings))))
with st.expander("About this company"):
    st.markdown(md(p.get("longBusinessSummary") or "No description available."))

"""stocklens: everything about a stock on one screen.  Run: streamlit run app.py"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from stocklens import DISCLAIMER, fmt, impact, invest, marketdata, scanner, universe
from stocklens.charts import (THEMES, financials_chart, lines_chart, price_chart, pulse_chart, target_chart,
                              vs_market_chart)
from stocklens.report import PERIODS, NoPriceData, build
from stocklens.search import search
from stocklens.symbols import resolve

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
WATCHLIST_FILE = Path.home() / ".stocklens" / "watchlist.json"
DEFAULT_WATCHLIST = ["AAPL", "NVDA", "RELIANCE.NS", "TCS.NS"]
SOFT = "opacity:.68;font-size:.86em"


# ------------------------------------------------------------------ helpers --
@st.cache_data(ttl=900, show_spinner=False)
def load(symbol, market, period, news, filings):
    return build(symbol, market, period, include_news=news, include_filings=filings)


@st.cache_data(ttl=600, show_spinner=False)
def quick(symbol):
    """Just enough for a watchlist card: recent closes."""
    import yfinance as yf
    hist = marketdata.history(yf.Ticker(resolve(symbol).yahoo), "6mo")
    return hist["Close"] if not hist.empty else pd.Series(dtype=float)


@st.cache_data(ttl=3600, show_spinner=False)
def find(query):
    return search(query)


@st.cache_data(ttl=900, show_spinner=False)
def run_scan(symbols: tuple[str, ...]):
    return scanner.scan(list(symbols))


def md(text: str) -> str:
    """Escape text for st.markdown: '$' would start LaTeX math and brackets break links."""
    return text.replace("$", "\\$").replace("[", "\\[").replace("]", "\\]")


def theme_mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except AttributeError:
        return "light"


def label(s: str) -> str:
    name = POPULAR.get(s) or st.session_state.get("names", {}).get(s)
    return f"{s} · {name}" if name else s


def read_watchlist() -> list[str]:
    try:
        return json.loads(WATCHLIST_FILE.read_text())
    except (OSError, ValueError):
        return DEFAULT_WATCHLIST


def save_watchlist() -> None:
    try:
        WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        WATCHLIST_FILE.write_text(json.dumps(st.session_state.watchlist))
    except OSError:
        pass


def open_stock(sym: str, name: str | None = None) -> None:
    if name:
        st.session_state.names[sym] = name
    st.session_state.stock = sym
    st.session_state.view = "Stock"


def soft(text: str) -> None:
    st.markdown(f"<span style='{SOFT}'>{md(text)}</span>", unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar --
if "stock" not in st.session_state:
    # run.py opens the page as ?symbol=TCS.NS so the dashboard starts on the stock you asked for.
    st.session_state.stock = (st.query_params.get("symbol") or "AAPL").strip().upper()
st.session_state.setdefault("watchlist", read_watchlist())
st.session_state.setdefault("names", {})
st.session_state.setdefault("view", "Stock")

with st.sidebar:
    st.title("📈 stocklens")
    st.caption("Everything about a stock, in one place")
    st.segmented_control("View", ["Stock", "Market scanner"], key="view", required=True,
                         label_visibility="collapsed")

    query = st.text_input("🔎 Find any company", placeholder="Name or symbol, e.g. Zomato, Nvidia",
                          help="Searches all US and Indian (NSE/BSE) listings")
    if query.strip():
        try:
            matches = find(query)
        except Exception:
            matches = None
            st.caption("Search is unavailable right now. You can still type a symbol below.")
        if matches == []:
            st.caption("No US or Indian stocks found. Try another spelling.")
        for q in matches or []:
            st.button(f"{q['symbol']} · {q['name']}", key=f"pick_{q['symbol']}", help=q["exchange"],
                      on_click=open_stock, args=(q["symbol"], q["name"]), width="stretch")

    options = list(dict.fromkeys([*POPULAR, *st.session_state.watchlist, st.session_state.stock]))
    symbol = st.selectbox("Stock", options, key="stock", accept_new_options=True, format_func=label,
                          help="Pick one, or type any symbol and press Enter: TSLA, WIPRO.NS, RELIANCE.BO")
    period = st.selectbox("Chart period", PERIODS, index=PERIODS.index("1y"))
    st.multiselect("Watchlist", list(dict.fromkeys([*POPULAR, *st.session_state.watchlist])),
                   key="watchlist", accept_new_options=True, format_func=label, max_selections=8,
                   on_change=save_watchlist, help="Shown as cards at the top. Type any symbol to add it.")
    with st.expander("Options"):
        market = MARKETS[st.radio("Market for bare symbols", list(MARKETS),
                                  help="Only needed for symbols typed without .NS / .BO")]
        show_cone = st.checkbox("Future range on chart", True)
        show_bands = st.checkbox("Bollinger bands", False)
        show_macd = st.checkbox("MACD panel", False)
        use_news = st.checkbox("News", True)
        use_filings = st.checkbox("SEC / NSE filings", True)
    st.caption(DISCLAIMER)

mode = theme_mode()
colors = THEMES[mode]


# ------------------------------------------------------------ scanner view --
def scanner_view() -> None:
    st.header("🔎 Market scanner")
    st.caption("Ranks many stocks at once on trend and performance. Click a row, then open it for the full picture.")
    lists = {**universe.UNIVERSES, "My watchlist": st.session_state.watchlist, "Custom list": []}
    c1, c2 = st.columns([1, 2])
    choice = c1.selectbox("Stocks to scan", list(lists))
    symbols = lists[choice]
    if choice == "Custom list":
        text = c2.text_input("Symbols, separated by commas", "AAPL, TSLA, INFY.NS, ETERNAL.NS")
        symbols = [s.strip().upper() for s in text.replace(";", ",").split(",") if s.strip()]
    if not symbols:
        st.info("Add some stocks to scan.")
        return
    with st.spinner(f"Scanning {len(symbols)} stocks…"):
        try:
            table, failed = run_scan(tuple(symbols))
        except Exception as exc:
            st.error(f"Couldn't download prices ({exc.__class__.__name__}). Check your internet connection.")
            return
    if table.empty:
        st.warning("No price data came back. Check your internet connection or the symbols.")
        return

    def top(col, n=4, ascending=False, where=None):
        df = table if where is None else table[where]
        return df[col].dropna().sort_values(ascending=ascending).head(n)

    boards = [
        ("🚀 Top gainers (1 month)", top("1M"), "1M"),
        ("📉 Biggest fallers (1 month)", top("1M", ascending=True), "1M"),
        ("🏔️ Near 52-week high", top("From 52w high"), "From 52w high"),
        ("🧊 Oversold (RSI under 35)", top("RSI", ascending=True, where=table["RSI"] < 35), "RSI"),
    ]
    for col, (title, series, kind) in zip(st.columns(4), boards):
        with col, st.container(border=True):
            st.markdown(f"**{title}**")
            if series.empty:
                soft("None right now")
            for sym, val in series.items():
                shown = (f"RSI {val:.0f}" if kind == "RSI" else "at high" if kind == "From 52w high" and val > -0.001
                         else fmt.pct(val))
                st.button(f"{sym}  {shown}", key=f"board_{title}_{sym}", on_click=open_stock, args=(sym,),
                          width="stretch")

    view = table.reset_index()
    view.insert(1, "Market", ["India" if s.endswith((".NS", ".BO")) else "US" for s in view["Symbol"]])
    view["Price"] = [fmt.price(p, resolve(s).market) for s, p in zip(view["Symbol"], view["Price"])]
    for col in ("1D", "1W", "1M", "3M", "1Y", "YTD", "From 52w high", "Volatility"):
        view[col] = view[col] * 100
    event = st.dataframe(
        view, hide_index=True, on_select="rerun", selection_mode="single-row", key="scan_table",
        height=min(36 * (len(view) + 1) + 4, 940),
        column_config={
            **{c: st.column_config.NumberColumn(format="%+.1f%%") for c in ("1D", "1W", "1M", "3M", "1Y", "YTD",
                                                                            "From 52w high")},
            "Volatility": st.column_config.NumberColumn(format="%.0f%%", help="Yearly swing size"),
            "RSI": st.column_config.NumberColumn(format="%.0f", help="Over 70 overbought, under 30 oversold"),
            "Trend": st.column_config.TextColumn(help="Price vs its 50- and 200-day averages"),
        })
    rows = event.selection.rows if event and event.selection else []
    if rows:
        sym = view.iloc[rows[0]]["Symbol"]
        st.button(f"Open {sym} →", type="primary", on_click=open_stock, args=(sym,))
    else:
        st.caption("Tip: click a row to select it, or sort by clicking a column header.")
    if failed:
        st.caption(f"Skipped (no data): {', '.join(failed)}")


if st.session_state.view == "Market scanner":
    scanner_view()
    st.stop()

if not symbol or not symbol.strip():
    st.info("Pick or search for a stock in the sidebar.")
    st.stop()

# ---------------------------------------------------------------- watchlist --
if st.session_state.watchlist:
    cards = st.columns(len(st.session_state.watchlist))
    for col, sym in zip(cards, st.session_state.watchlist):
        with col:
            try:
                closes = quick(sym)
            except Exception:
                closes = pd.Series(dtype=float)
            mk = resolve(sym).market
            if len(closes) >= 2:
                change = closes.iloc[-1] / closes.iloc[-2] - 1
                st.metric(sym, fmt.price(closes.iloc[-1], mk), fmt.pct(change), border=True,
                          chart_data=closes.iloc[-63:].round(2).tolist(), chart_type="line")
            else:
                st.metric(sym, "-", border=True)
            st.button("Open", key=f"open_{sym}", on_click=open_stock, args=(sym,),
                      type="primary" if sym == symbol else "secondary", width="stretch")

# -------------------------------------------------------------------- data --
try:
    with st.spinner(f"Fetching {symbol.upper()}: prices, financials, filings, news…"):
        r = load(symbol, market, period, use_news, use_filings)
except NoPriceData as exc:
    st.error(str(exc))
    st.stop()

m = r.ticker.market
p = r.profile
perf = r.performance
st.session_state.names.setdefault(r.ticker.yahoo, marketdata.search_name(r.name))

# --------------------------------------------------------------------- hero --
st.header(f"{r.name}")
with st.container(horizontal=True):
    st.badge(r.ticker.yahoo, color="primary")
    st.badge(f"{r.ticker.exchange} · {m.name}", color="gray")
    if p.get("sector"):
        st.badge(p["sector"], color="gray")
    tone_color = {"Bullish leaning": "green", "Bearish leaning": "red"}.get(r.verdict, "gray")
    st.badge(f"Trend: {r.verdict}", color=tone_color)
    if r.red_flags:
        st.badge(f"{len(r.red_flags)} red flag{'s' if len(r.red_flags) > 1 else ''}", icon="⚠️", color="red")

left, right = st.columns([3, 2], gap="large")
with left, st.container(border=True):
    st.markdown("**🧭 Briefing**")
    st.markdown("\n".join(f"- {md(line)}" for line in r.briefing))
with right:
    c = st.columns(2)
    c[0].metric("Price", fmt.price(r.last_close, m), fmt.pct(perf["1D"]), border=True)
    c[1].metric("1 year", fmt.pct(perf["1Y"]), border=True)
    c = st.columns(2)
    score = f"{r.checklist_score:.1f}/10" if r.checklist_score is not None else "-"
    c[0].metric("Checklist", score, r.checklist_label, delta_color="off", delta_arrow="off", border=True)
    if r.relative:
        c[1].metric(f"vs {m.benchmark_name} (1y)", fmt.pct(r.relative["gap"]), border=True,
                    help="Stock's 1-year return minus the index's")
    else:
        c[1].metric("Market cap", fmt.money(p.get("marketCap"), m), border=True)

tab_overview, tab_news, tab_fin, tab_mkt, tab_calc, tab_about = st.tabs(
    ["📈 Overview", "📰 News & impact", "💰 Financials", "🏁 Vs market & backtest", "🧮 Calculator", "ℹ️ About"])

# ----------------------------------------------------------------- overview --
with tab_overview:
    st.plotly_chart(price_chart(r.prices, r.timeline, m, mode, show_bands, show_macd,
                                cone=r.cone if show_cone else None),
                    theme=None, config={"displaylogo": False})
    st.caption("Markers sit on the first trading day each item could affect: ✕ red flag · ▲ positive · "
               "▼ negative · ● neutral/filing. The shaded area shows where the price is likely to be, "
               "based on how much it usually moves, not a prediction of direction.")

    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        st.subheader("✅ Investment checklist")
        if r.checklist_score is not None:
            st.markdown(f"### {r.checklist_score:.1f} / 10 · {r.checklist_label}")
        for pl in r.pillars:
            head = f"**{pl.name}** · {pl.score:.1f}/10" if pl.score is not None else f"**{pl.name}** · not enough data"
            st.markdown(f"{head}  \n<span style='{SOFT}'>{pl.question}</span>", unsafe_allow_html=True)
            st.progress(min(max((pl.score or 0) / 10, 0.0), 1.0))
            if pl.reasons:
                st.caption(md(" · ".join(pl.reasons)))
        st.caption("Rules of thumb, not advice. A fast grower can deserve a high P/E, and debt "
                   "ratios mean little for banks, so read the reasons.")

    with right, st.container(border=True):
        st.subheader("🔮 Outlook")
        st.caption("Nobody can predict exact prices. These are ranges and history-based odds.")
        if not r.ranges.empty:
            st.markdown("**Where the price is likely to be**")
            st.dataframe(pd.DataFrame({
                "In": r.ranges.index,
                "Likely (50%)": [f"{fmt.price(a, m)} – {fmt.price(b, m)}" for a, b in zip(r.ranges.low50, r.ranges.high50)],
                "Very likely (90%)": [f"{fmt.price(a, m)} – {fmt.price(b, m)}" for a, b in zip(r.ranges.low90, r.ranges.high90)],
                "Typical move": [f"±{v:.0%}" for v in r.ranges.typical_move],
            }), hide_index=True)
        if r.analogs:
            st.markdown(f"**After days like today**  \n<span style='{SOFT}'>{md(r.analogs['setup'])}</span>",
                        unsafe_allow_html=True)
            for row in r.analogs["rows"]:
                st.markdown(f"- {row['horizon']} later: higher **{row['pct_higher']:.0%}** of the time, median "
                            f"**{fmt.pct(row['median'])}** (all days: {row['pct_higher_all']:.0%}, "
                            f"{fmt.pct(row['median_all'])}; {row['matches']} matching days)")
        if r.track:
            acc, base = r.track["accuracy"], r.track["always_up"]
            text = (f"this method called the 1-month direction right **{acc:.0%}** of the time in "
                    f"{r.track['tests']} past tests, vs **{base:.0%}** for always guessing 'up'.")
            if acc > base + 0.03:
                st.success("Track record: " + text)
            else:
                st.warning("Track record: " + text + " It hasn't beaten the simple guess on this stock, "
                           "so treat the odds above with caution.")
        if r.backtest:
            b = r.backtest
            st.markdown(f"**Trend rule vs buy-and-hold** ({b['years']:.1f} years)  \n"
                        f"Owning it only while above the 200-day average: **{fmt.pct(b['rule']['total'])}** "
                        f"(worst drop {fmt.pct(b['rule']['max_drawdown'])}) vs buy-and-hold "
                        f"**{fmt.pct(b['hold']['total'])}** (worst drop {fmt.pct(b['hold']['max_drawdown'])}).")

    st.markdown("**📉📈 Biggest moves & possible causes**")
    for mv in r.moves:
        with st.expander(f"{mv.day:%d %b %Y}  ·  {fmt.pct(mv.change)}"):
            if mv.causes:
                for cause in mv.causes:
                    flag = "⚠️ " if cause.red_flag else ""
                    st.markdown(f"- {flag}[{md(cause.title)}]({cause.url}) — {md(cause.source)}" if cause.url
                                else f"- {flag}{md(cause.title)} — {md(cause.source)}")
            else:
                st.caption("No matching news or filing found for this day.")

# ------------------------------------------------------------ news & impact --
IMPACT_COLOR = {"Positive": "green", "Negative": "red", "Unclear": "gray"}


def news_card(item, stats, typical: float) -> None:
    direction, strength = impact.rating(item, stats)
    with st.container(border=True):
        row = st.container(horizontal=True)
        with row:
            arrow = {"Positive": "▲", "Negative": "▼", "Unclear": "●"}[direction]
            st.badge(f"{arrow} {direction} · {strength} impact", color=IMPACT_COLOR[direction])
            when = item.when.tz_convert(m.timezone).strftime("%d %b %Y" + (", %H:%M" if item.has_time else ""))
            st.badge(f"{when} · {item.source}", color="gray")
            if item.kind == "filing":
                st.badge("Official filing", icon="📄", color="blue")
        st.markdown(f"**[{md(item.title)}]({item.url})**" if item.url else f"**{md(item.title)}**")
        if item.detail and item.kind == "filing":
            soft(item.detail)
        if item.reaction is not None:
            big = pd.notna(typical) and abs(item.reaction) >= 2 * typical
            st.caption(f"Stock moved {fmt.pct(item.reaction)} on {item.reaction_day:%d %b}"
                       + (" (a big move for this stock)" if big else ""))


with tab_news:
    stats = r.topic_stats
    typical = impact.typical_move(r.history)
    now = r.history.index[-1]
    month = [i for i in r.timeline if i.kind == "news" and i.when >= now - pd.Timedelta(days=30)]
    pos = sum(1 for i in month if i.sentiment > 0 and not i.red_flag)
    neg = sum(1 for i in month if i.sentiment < 0 or i.red_flag)
    movers = [s for s in stats.values() if s.days >= 3 and pd.notna(s.vs_normal)]
    loudest = max(movers, key=lambda s: s.vs_normal, default=None)

    c = st.columns(4)
    c[0].metric("Headlines (30 days)", len(month), border=True)
    c[1].metric("Tone (30 days)", f"{pos} ▲ · {neg} ▼", border=True,
                help="Positive vs negative headlines, from keyword rules")
    c[2].metric("Red flags (chart period)", len(r.red_flags), border=True)
    c[3].metric("Moves this stock most", impact.SHORT[loudest.topic] if loudest else "-",
                f"{loudest.vs_normal:.1f}× a normal day" if loudest else None,
                delta_color="off", delta_arrow="off", border=True,
                help="Which kind of news has caused the biggest price moves here")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("**News pulse** · headlines per week")
        pulse = impact.pulse(r.timeline, now=pd.Timestamp(now).tz_convert("UTC"))
        if pulse.to_numpy().sum():
            st.plotly_chart(pulse_chart(pulse, mode), theme=None,
                            config={"displaylogo": False, "displayModeBar": False})
        else:
            soft("No headlines in the last 12 weeks.")
    with right:
        st.markdown("**📅 Coming up**")
        if r.upcoming:
            for e in r.upcoming:
                with st.container(border=True):
                    st.markdown(f"**{e.when.tz_convert(m.timezone):%d %b %Y}** · {md(e.title)}"
                                + (f" ({md(e.detail)})" if e.detail else ""))
                    es = stats.get("earnings") if "earnings" in e.tags else stats.get("dividend/buyback")
                    if "earnings" in e.tags:
                        txt = "Results day is usually the biggest scheduled event for a stock."
                        if es and es.days >= 3:
                            txt += (f" Past results days moved it {es.avg_size:.1%} on average "
                                    f"({es.vs_normal:.1f}× a normal day), closing higher {es.up_share:.0%} of the time.")
                    else:
                        txt = "On the ex-dividend date the price usually drops by about the dividend amount."
                    soft(txt)
        else:
            soft("No upcoming earnings or dividend dates found.")

    if stats:
        st.markdown(f"**How news has moved {r.ticker.base}** · on the first trading day each item could affect")
        rows = sorted(stats.values(), key=lambda s: impact.TOPICS.index(s.topic))
        st.dataframe(pd.DataFrame({
            "News type": [f"{impact.ICONS[s.topic]} {impact.TITLES[s.topic]}" for s in rows],
            "Days": [s.days for s in rows],
            "Average move": [s.avg_move * 100 for s in rows],
            "Typical size": [s.avg_size * 100 for s in rows],
            "Closed higher": [s.up_share * 100 for s in rows],
            "vs a normal day": [s.vs_normal for s in rows],
        }), hide_index=True, column_config={
            "Average move": st.column_config.NumberColumn(format="%+.2f%%"),
            "Typical size": st.column_config.NumberColumn(format="%.2f%%", help="Average size of the move, up or down"),
            "Closed higher": st.column_config.NumberColumn(format="%.0f%%"),
            "vs a normal day": st.column_config.NumberColumn(format="%.1f×", help=f"Normal day: ±{typical:.2%}"),
        })
        st.caption("Few days means weak evidence. Headlines only go back a few months; filings and earnings go back years.")

    groups = impact.grouped(r.timeline)
    if not groups:
        st.info("No recent news or filings found for this company.")
    for topic, items in groups.items():
        st.markdown(f"#### {impact.ICONS[topic]} {impact.TITLES[topic]} · {len(items)}")
        lines = [f"**{lbl}:** {md(txt)}" if lbl else md(txt) for lbl, txt in impact.explain_group(topic, items)]
        st.info("**What this kind of news means**  \n" + "  \n".join(lines), icon="💡")
        for item in items[:4]:
            news_card(item, stats, typical)
        if len(items) > 4:
            with st.expander(f"Show {len(items) - 4} more"):
                for item in items[4:20]:
                    news_card(item, stats, typical)
    st.caption("Tags and tone come from keyword rules on headlines, so read the article before acting on it.")

    with st.expander("🗞️ Full timeline (news, filings & events) as a table"):
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

# --------------------------------------------------------------- financials --
with tab_fin:
    st.markdown("**Valuation & quality**")
    de = p.get("debtToEquity")
    facts = [
        ("Market cap", fmt.money(p.get("marketCap"), m)),
        ("P/E", fmt.number(p.get("trailingPE"), 1)),
        ("Forward P/E", fmt.number(p.get("forwardPE"), 1)),
        ("Price / book", fmt.number(p.get("priceToBook"), 1)),
        ("Profit margin", fmt.pct(p.get("profitMargins"), signed=False)),
        ("Return on equity", fmt.pct(p.get("returnOnEquity"), signed=False)),
        ("Revenue growth (y/y)", fmt.pct(p.get("revenueGrowth"))),
        ("Debt / equity", f"{de / 100:.2f}x" if isinstance(de, (int, float)) else "-"),
        ("Dividend yield", fmt.pct(r.dividend_yield, signed=False) if r.dividend_yield else "-"),
        ("Beta (vs index)", fmt.number(r.relative["beta"]) if r.relative else "-"),
        ("Insiders own", fmt.pct(p.get("heldPercentInsiders"), signed=False)),
        ("Institutions own", fmt.pct(p.get("heldPercentInstitutions"), signed=False)),
    ]
    for start in range(0, len(facts), 4):
        for col, (k, v) in zip(st.columns(4), facts[start:start + 4]):
            col.metric(k, v, border=True)

    low, mean, high = p.get("targetLowPrice"), p.get("targetMeanPrice"), p.get("targetHighPrice")
    if all(isinstance(v, (int, float)) for v in (low, mean, high)):
        n = p.get("numberOfAnalystOpinions")
        rec = (p.get("recommendationKey") or "").replace("_", " ")
        st.markdown("**Analyst price targets**" + (f" · {n} analysts" if n else "")
                    + (f" · consensus: **{rec}**" if rec and rec != "none" else ""))
        st.plotly_chart(target_chart(r.last_close, low, mean, high, m, mode), theme=None,
                        config={"displaylogo": False, "displayModeBar": False})
        st.caption("Analysts are often wrong and tend to be optimistic, so treat targets as one opinion.")

    st.markdown("**Revenue & profit**")
    tq, ta = st.tabs(["Quarterly", "Annual"])
    for tab, df, freq in ((tq, r.quarterly, "quarterly"), (ta, r.annual, "annual")):
        with tab:
            if df.empty or "Revenue" not in df:
                st.caption("Financial statements not available for this stock.")
                continue
            st.plotly_chart(financials_chart(df, m, mode, freq), theme=None, config={"displaylogo": False})
            st.dataframe(pd.DataFrame({
                "Period end": df.index.strftime("%Y-%m-%d"),
                "Revenue": [fmt.money(v, m) for v in df["Revenue"]],
                "Net profit": [fmt.money(v, m) for v in df.get("Net profit", [None] * len(df))],
                "Net margin": [fmt.pct(v, signed=False) for v in df.get("Net margin", [None] * len(df))],
                "EPS": [fmt.number(v) for v in df.get("EPS", [None] * len(df))],
                "Revenue growth": [fmt.pct(v) for v in df["Revenue growth"]],
            }), hide_index=True)

# --------------------------------------------------------- market & backtest --
with tab_mkt:
    st.markdown(f"**{r.ticker.base} vs {m.benchmark_name}** (both start at 100)")
    fig = (vs_market_chart(r.prices["Close"], r.benchmark, r.ticker.base, m.benchmark_name, mode)
           if not r.benchmark.empty else None)
    if fig:
        st.plotly_chart(fig, theme=None, config={"displaylogo": False})
    if r.relative:
        c = st.columns(3)
        c[0].metric(f"{r.ticker.base} (1y)", fmt.pct(r.relative["stock"]), border=True)
        c[1].metric(f"{m.benchmark_name} (1y)", fmt.pct(r.relative["index"]), border=True)
        c[2].metric("Beta", fmt.number(r.relative["beta"]), border=True,
                    help="How much the stock tends to move when the index moves 1%. Above 1 = swings more.")
    elif not fig:
        st.caption("Index data not available.")

    if r.backtest:
        b = r.backtest
        st.markdown(f"**Backtest: trend rule vs buy-and-hold** (growth of 100 over {b['years']:.1f} years)")
        st.plotly_chart(lines_chart(b["equity"] * 100, [colors["series"][0], colors["series"][1]], mode,
                                    "Growth of 100"), theme=None, config={"displaylogo": False})
        c = st.columns(4)
        c[0].metric("Buy and hold", fmt.pct(b["hold"]["total"]), f"worst drop {fmt.pct(b['hold']['max_drawdown'])}",
                    delta_color="off", delta_arrow="off", border=True)
        c[1].metric("Trend rule", fmt.pct(b["rule"]["total"]), f"worst drop {fmt.pct(b['rule']['max_drawdown'])}",
                    delta_color="off", delta_arrow="off", border=True)
        c[2].metric("Time invested", f"{b['time_invested']:.0%}", border=True)
        c[3].metric("Buy/sell switches", b["switches"], border=True)
        st.caption("Trend rule: own the stock only while its price is above the 200-day average, acting the "
                   "next day. Ignores costs and taxes. It usually avoids the worst crashes but can miss rebounds.")

# --------------------------------------------------------------- calculator --
with tab_calc:
    span_years = (r.history.index[-1] - r.history.index[0]).days / 365.25
    choices = [y for y in (1, 3, 5, 10) if y <= span_years + 0.05] or [1]
    c = st.columns(3)
    years = c[0].selectbox("Years ago", choices, index=len(choices) - 1)
    lump = c[1].number_input(f"One-time amount ({m.currency_sign})", min_value=1.0,
                             value=10000.0 if m.code == "IN" else 1000.0, step=1000.0 if m.code == "IN" else 100.0)
    monthly = c[2].number_input(f"Monthly SIP ({m.currency_sign})", min_value=1.0,
                                value=5000.0 if m.code == "IN" else 500.0, step=500.0 if m.code == "IN" else 50.0)
    close = r.history["Close"]
    ls, sp = invest.lump_sum(close, lump, years), invest.sip(close, monthly, years)
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        st.markdown(f"**One-time investment** of {fmt.price(lump, m)}")
        if ls:
            st.metric(f"Worth today (bought {ls['start']:%d %b %Y})", fmt.price(ls["value"], m),
                      f"{fmt.pct(ls['total_return'])} total · {fmt.pct(ls['cagr'])} a year")
    with right, st.container(border=True):
        st.markdown(f"**Monthly SIP** of {fmt.price(monthly, m)}")
        if sp:
            st.metric(f"Worth today ({sp['instalments']} instalments, {fmt.price(sp['invested'], m)} put in)",
                      fmt.price(sp["value"], m), f"{fmt.pct(sp['total_return'])} total · XIRR {fmt.pct(sp['xirr'])}")
    if sp:
        st.plotly_chart(lines_chart(sp["path"], [colors["muted"], colors["series"][0]], mode,
                                    f"{m.currency_sign}", "%{y:,.0f}"), theme=None, config={"displaylogo": False})
    st.caption("Uses dividend-adjusted prices (dividends reinvested). Ignores taxes and brokerage. "
               "Past returns don't guarantee future returns.")

# -------------------------------------------------------------------- about --
with tab_about:
    st.markdown(md(p.get("longBusinessSummary") or "No company description available."))
    st.markdown("""
**How stocklens works**
- **Briefing**: everything on this page, condensed into plain sentences.
- **Future range**: thousands of simulated paths that replay this stock's own past daily moves
  (re-centred so no trend is assumed). The band shows how far it typically moves, not which way.
- **Days like today**: past days with the same trend (above/below the 200-day average) and momentum
  (RSI band), and what the price did 1 and 3 months later. The *track record* re-runs this test
  through history using only information available at each point.
- **News & impact**: headlines (Google News, Yahoo Finance) and official filings (SEC for US, NSE for
  India), grouped by type, each with what that kind of news usually means and how much it has moved
  this stock before.
- **Checklist**: six pillars scored with common rules of thumb; reasons are shown for each score.
""")
    st.caption(DISCLAIMER)

if r.warnings:
    st.warning(md("Some data couldn't be loaded: " + "; ".join(dict.fromkeys(r.warnings))))

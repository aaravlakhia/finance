"""Plotly charts for the dashboard. Only needed for `streamlit run app.py`."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import fmt
from .models import Item

# Colour-blind-checked series colours, stepped separately for light and dark backgrounds.
THEMES = {
    "light": {"series": ["#2a78d6", "#eb6834", "#1baf7a"], "ink": "#0b0b0b", "ink2": "#52514e",
              "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb"},
    "dark": {"series": ["#3987e5", "#d95926", "#199e70"], "ink": "#f0efec", "ink2": "#c3c2b7",
             "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835", "surface": "#1a1a19"},
}

# Event markers: (label, colour, marker shape). Shape + legend label mean colour is never the only cue.
EVENT_STYLES = {
    "red_flag": ("Red flag", "#d03b3b", "x"),
    "negative": ("Negative news", "#ec835a", "triangle-down"),
    "positive": ("Positive news", "#0ca30c", "triangle-up"),
    "neutral": ("Neutral / filing", "#898781", "circle"),
}


def _event_style(item: Item) -> str:
    if item.red_flag:
        return "red_flag"
    return {1: "positive", -1: "negative"}.get(item.sentiment, "neutral")


def _short(text: str, n: int = 90) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _add_end_labels(fig: go.Figure, labels: list, values: pd.DataFrame, t: dict) -> None:
    """Name each line at its right end, nudging labels apart so they never overlap."""
    if not labels:
        return
    lo, hi = values.min().min(), values.max().max()
    gap = (hi - lo) * 0.045
    labels.sort(key=lambda lab: lab[0])
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + gap)
    for y, text, x in labels:
        fig.add_annotation(x=x, y=y, text=text, showarrow=False, xanchor="left", xshift=6,
                           font=dict(color=t["ink2"], size=11), row=1, col=1)


def _base_layout(fig: go.Figure, t: dict, height: int) -> None:
    fig.update_layout(
        height=height, margin=dict(l=64, r=96, t=36, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=t["ink2"], size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    font=dict(color=t["ink2"]), traceorder="normal"),
        hovermode="x unified",
        hoverlabel=dict(font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif")),
    )
    fig.update_xaxes(showgrid=False, linecolor=t["axis"], tickfont=dict(color=t["muted"]),
                     showspikes=True, spikecolor=t["muted"], spikethickness=1, spikemode="across")
    fig.update_yaxes(gridcolor=t["grid"], gridwidth=1, zeroline=False, linecolor=t["axis"],
                     tickfont=dict(color=t["muted"]))


def _add_cone(fig: go.Figure, prices: pd.DataFrame, cone: pd.DataFrame, market, mode: str) -> None:
    """Shaded future ranges, joined to today's close so they fan out from the last price."""
    t = THEMES[mode]
    outer, inner = (("rgba(42,120,214,0.10)", "rgba(42,120,214,0.22)") if mode == "light"
                    else ("rgba(57,135,229,0.16)", "rgba(57,135,229,0.32)"))
    last = prices["Close"].iloc[-1]
    c = pd.concat([pd.DataFrame({col: [last] for col in cone.columns}, index=[prices.index[-1]]), cone])
    cs = market.currency_sign
    for hi, lo, fill, label in (("p95", "p05", outer, "Very likely range (90%)"),
                                ("p75", "p25", inner, "Likely range (50%)")):
        fig.add_trace(go.Scatter(x=c.index, y=c[hi], line=dict(width=0), hoverinfo="skip", showlegend=False),
                      row=1, col=1)
        fig.add_trace(go.Scatter(
            x=c.index, y=c[lo], line=dict(width=0), fill="tonexty", fillcolor=fill, name=label, legendrank=30,
            customdata=c[[lo, hi]].to_numpy(),
            hovertemplate=f"{label}: {cs}%{{customdata[0]:,.2f}} – {cs}%{{customdata[1]:,.2f}}<extra></extra>"),
            row=1, col=1)
    fig.add_trace(go.Scatter(x=c.index, y=c["p50"], line=dict(color=t["series"][0], width=1.5, dash="dot"),
                             name="Middle of range", hoverinfo="skip", legendrank=29), row=1, col=1)
    fig.add_vline(x=prices.index[-1], line=dict(color=t["axis"], width=1), row=1, col=1)
    fig.add_annotation(x=prices.index[-1], y=1, yref="y domain", text="today", showarrow=False,
                       xanchor="left", yanchor="top", xshift=4, font=dict(color=t["muted"], size=10))


def price_chart(prices: pd.DataFrame, items: list[Item], market, mode: str = "light",
                show_bands: bool = False, show_macd: bool = False, cone: pd.DataFrame | None = None) -> go.Figure:
    t = THEMES[mode]
    s = t["series"]
    rows = 4 if show_macd else 3
    heights = [0.55, 0.12, 0.17, 0.16] if show_macd else [0.62, 0.14, 0.24]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.035,
                        row_heights=heights)
    x = prices.index

    if show_bands:
        fig.add_trace(go.Scatter(x=x, y=prices["BB_upper"], line=dict(width=0), hoverinfo="skip",
                                 showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=prices["BB_lower"], line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(137,135,129,0.14)", name="Bollinger band",
                                 hoverinfo="skip"), row=1, col=1)

    if cone is not None and not cone.empty:
        _add_cone(fig, prices, cone, market, mode)

    lines = [("Close", "Close", s[0], 2), ("SMA50", "50-day avg", s[1], 1.5), ("SMA200", "200-day avg", s[2], 1.5)]
    end_labels = []
    for col, label, color, width in lines:
        series = prices[col]
        if series.notna().any():
            fig.add_trace(go.Scatter(x=x, y=series, name=label, line=dict(color=color, width=width),
                                     legendrank=len(end_labels) + 1,
                                     hovertemplate=f"{label}: {market.currency_sign}%{{y:,.2f}}<extra></extra>"),
                          row=1, col=1)
            last = series.dropna()
            end_labels.append([last.iloc[-1], label, last.index[-1]])
    _add_end_labels(fig, end_labels, prices[["Close", "SMA50", "SMA200"]], t)

    # One marker per trading day per tone, placed on the price line.
    close_by_day = pd.Series(prices["Close"].to_numpy(), index=prices.index.date)
    groups: dict[tuple, list[Item]] = {}
    for item in items:
        if item.reaction_day is not None and item.reaction_day in close_by_day.index:
            groups.setdefault((_event_style(item), item.reaction_day), []).append(item)
    for style, (label, color, symbol) in EVENT_STYLES.items():
        days = sorted(d for (st, d) in groups if st == style)
        if not days:
            continue
        hover = []
        for d in days:
            its = groups[(style, d)]
            lines_ = [f"• {_short(i.title)} ({i.source})" for i in its[:4]]
            if len(its) > 4:
                lines_.append(f"…and {len(its) - 4} more")
            move = its[0].reaction
            head = f"<b>{label}</b>" + (f" · move that day {fmt.pct(move)}" if move is not None else "")
            hover.append(head + "<br>" + "<br>".join(lines_))
        idx = [pd.Timestamp(d) for d in days]
        if prices.index.tz is not None:
            idx = [i.tz_localize(prices.index.tz) for i in idx]
        fig.add_trace(go.Scatter(
            x=idx, y=[close_by_day[d] for d in days], mode="markers", name=label,
            marker=dict(symbol=symbol, size=11, color=color, line=dict(color=t["surface"], width=2)),
            hovertext=hover, hovertemplate="%{hovertext}<extra></extra>"), row=1, col=1)

    fig.add_trace(go.Bar(x=x, y=prices["Volume"], name="Volume", marker=dict(color=t["muted"], line=dict(width=0)),
                         opacity=0.55, showlegend=False, hovertemplate="Volume: %{y:,.0f}<extra></extra>"),
                  row=2, col=1)

    fig.add_trace(go.Scatter(x=x, y=prices["RSI14"], name="RSI (14)", line=dict(color=s[0], width=1.5),
                             showlegend=False, hovertemplate="RSI: %{y:.0f}<extra></extra>"), row=3, col=1)
    for level, text in ((70, "overbought 70"), (30, "oversold 30")):
        fig.add_hline(y=level, line=dict(color=t["axis"], width=1), row=3, col=1,
                      annotation_text=text, annotation_position="right",
                      annotation_font=dict(color=t["muted"], size=10))

    if show_macd:
        fig.add_trace(go.Bar(x=x, y=prices["MACD_hist"], marker=dict(color=t["muted"], line=dict(width=0)),
                             opacity=0.55, showlegend=False, hovertemplate="Histogram: %{y:.2f}<extra></extra>"),
                      row=4, col=1)
        fig.add_trace(go.Scatter(x=x, y=prices["MACD"], line=dict(color=s[0], width=1.5), showlegend=False,
                                 hovertemplate="MACD: %{y:.2f}<extra></extra>"), row=4, col=1)
        fig.add_trace(go.Scatter(x=x, y=prices["MACD_signal"], line=dict(color=s[1], width=1.5),
                                 showlegend=False, hovertemplate="Signal: %{y:.2f}<extra></extra>"), row=4, col=1)
        fig.update_yaxes(title_text="MACD", row=4, col=1)

    _base_layout(fig, t, 720 if show_macd else 640)
    fig.update_yaxes(title_text=f"Price ({market.currency_sign})", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], tickvals=[30, 50, 70], row=3, col=1)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def financials_chart(statement: pd.DataFrame, market, mode: str = "light", freq: str = "quarterly") -> go.Figure:
    t = THEMES[mode]
    s = t["series"]
    if market.code == "IN":
        scale, unit = 1e7, f"{market.currency_sign} Cr"
    else:
        biggest = statement["Revenue"].abs().max()
        scale, unit = (1e9, f"{market.currency_sign}B") if biggest >= 1e9 else (1e6, f"{market.currency_sign}M")
    labels = [d.strftime("%Y-%m" if freq == "quarterly" else "FY%Y") for d in statement.index]
    fig = go.Figure()
    for col, color in (("Revenue", s[0]), ("Net profit", s[1])):
        if col in statement:
            fig.add_trace(go.Bar(x=labels, y=statement[col] / scale, name=col,
                                 marker=dict(color=color, line=dict(width=0)),
                                 hovertemplate=f"{col}: %{{y:,.1f}} {unit}<extra></extra>"))
    _base_layout(fig, t, 340)
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.06, barcornerradius=4,
                      margin=dict(l=64, r=8, t=36, b=40))
    fig.update_xaxes(showspikes=False, type="category")
    fig.update_yaxes(title_text=unit)
    return fig


def lines_chart(df: pd.DataFrame, colors: list[str], mode: str = "light", y_title: str = "",
                hover: str = "%{y:,.1f}", height: int = 320) -> go.Figure:
    """Several lines on one shared axis, each named at its right end."""
    t = THEMES[mode]
    fig = make_subplots(rows=1, cols=1)
    labels = []
    for col, color in zip(df.columns, colors):
        series = df[col].dropna()
        if series.empty:
            continue
        fig.add_trace(go.Scatter(x=series.index, y=series, name=col, line=dict(color=color, width=2),
                                 hovertemplate=f"{col}: {hover}<extra></extra>"), row=1, col=1)
        labels.append([series.iloc[-1], col, series.index[-1]])
    _add_end_labels(fig, labels, df, t)
    _base_layout(fig, t, height)
    fig.update_layout(margin=dict(l=64, r=120, t=36, b=40))
    fig.update_yaxes(title_text=y_title)
    return fig


def vs_market_chart(close: pd.Series, bench: pd.Series, name: str, bench_name: str,
                    mode: str = "light") -> go.Figure | None:
    """Stock and index both rebased to 100 at the start of the window (one shared axis)."""
    def by_day(sr):
        idx = sr.index.tz_localize(None) if sr.index.tz is not None else sr.index
        return pd.Series(sr.to_numpy(), index=idx.normalize())

    both = pd.concat([by_day(close), by_day(bench)], axis=1, keys=[name, bench_name], sort=True).dropna()
    both = both[both.index >= by_day(close).index[0]]
    if len(both) < 2:
        return None
    t = THEMES[mode]
    return lines_chart(both / both.iloc[0] * 100, [t["series"][0], t["muted"]], mode,
                       "Growth of 100", "%{y:,.1f}")


def target_chart(price: float, low: float, mean: float, high: float, market, mode: str = "light") -> go.Figure:
    """Analysts' low / average / high price targets against today's price."""
    t = THEMES[mode]
    cs = market.currency_sign
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[low, high], y=[0, 0], mode="lines", line=dict(color=t["axis"], width=6),
                             hoverinfo="skip", showlegend=False))
    points = [(low, f"Low {cs}{low:,.0f}", t["muted"], "line-ns", 16, "top center"),
              (high, f"High {cs}{high:,.0f}", t["muted"], "line-ns", 16, "top center"),
              (mean, f"Avg target {cs}{mean:,.0f}", t["series"][0], "circle", 13, "top center"),
              (price, f"Now {cs}{price:,.0f}", t["ink"], "diamond", 12, "bottom center")]
    for x, text, color, symbol, size, pos in points:
        fig.add_trace(go.Scatter(x=[x], y=[0], mode="markers+text", text=[text], textposition=pos,
                                 textfont=dict(color=t["ink2"], size=11), showlegend=False,
                                 marker=dict(color=color, symbol=symbol, size=size,
                                             line=dict(color=color if symbol == "line-ns" else t["surface"], width=2)),
                                 hovertemplate=f"{text}<extra></extra>"))
    _base_layout(fig, t, 150)
    lo_x, hi_x = min(low, price), max(high, price)
    pad = (hi_x - lo_x) * 0.12 or 1
    fig.update_layout(margin=dict(l=24, r=24, t=10, b=10), hovermode="closest")
    fig.update_xaxes(range=[lo_x - pad, hi_x + pad], showspikes=False, showticklabels=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(visible=False, range=[-1, 1])
    return fig


def pulse_chart(table: pd.DataFrame, mode: str = "light") -> go.Figure:
    """Headlines per week: positive and neutral stacked above the line, negative below it."""
    t = THEMES[mode]
    fig = go.Figure()
    spec = (("Positive", "#0ca30c", 1), ("Neutral", t["muted"], 1), ("Negative", "#d03b3b", -1))
    for col, color, sign in spec:
        fig.add_trace(go.Bar(x=table.index, y=table[col] * sign, name=col,
                             marker=dict(color=color, line=dict(width=0)), customdata=table[col],
                             hovertemplate=f"{col}: %{{customdata}} headline(s)<extra></extra>"))
    _base_layout(fig, t, 260)
    fig.update_layout(barmode="relative", bargap=0.35, barcornerradius=3, margin=dict(l=48, r=8, t=36, b=36))
    fig.update_xaxes(showspikes=False, tickformat="%d %b")
    top = int((table["Positive"] + table["Neutral"]).max())
    bottom = int(table["Negative"].max())
    step = max(1, (top + bottom) // 6)
    ticks = list(range(-bottom, top + 1, step)) or [0]
    fig.update_yaxes(title_text="Headlines", zeroline=True, zerolinecolor=t["axis"], zerolinewidth=1,
                     tickvals=ticks, ticktext=[str(abs(v)) for v in ticks])  # counts below the line are negatives
    return fig

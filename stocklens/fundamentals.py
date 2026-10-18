"""Revenue, profit, margins and EPS from Yahoo Finance income statements."""

import logging

import pandas as pd

log = logging.getLogger(__name__)

# Output column -> Yahoo row names to try, in order.
ROWS = {
    "Revenue": ["Total Revenue", "Operating Revenue"],
    "Operating income": ["Operating Income"],
    "Net profit": ["Net Income", "Net Income Common Stockholders"],
    "EPS": ["Diluted EPS", "Basic EPS"],
}


def summarize(statement: pd.DataFrame | None) -> pd.DataFrame:
    """Reshape a Yahoo income statement into tidy rows, oldest period first.

    Columns: Revenue, Operating income, Net profit, EPS, Net margin, Revenue growth.
    """
    if statement is None or statement.empty:
        return pd.DataFrame()
    out = {}
    for col, candidates in ROWS.items():
        for name in candidates:
            if name in statement.index:
                out[col] = pd.to_numeric(statement.loc[name], errors="coerce")
                break
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.dropna(how="all")
    if "Revenue" in df:
        # Yahoo often pads the oldest column with NaN; drop periods with no revenue.
        df = df[df["Revenue"].notna()]
        if "Net profit" in df:
            df["Net margin"] = df["Net profit"] / df["Revenue"]
        df["Revenue growth"] = df["Revenue"].pct_change()
    df.index.name = "Period end"
    return df


def fetch(yt) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Return (quarterly, annual, warnings) for a yfinance Ticker."""
    warnings = []
    quarterly = annual = pd.DataFrame()
    try:
        quarterly = summarize(yt.quarterly_income_stmt)
    except Exception as exc:  # network / parsing problems shouldn't stop the report
        log.debug("quarterly financials failed", exc_info=True)
        warnings.append(f"Quarterly financials unavailable ({exc.__class__.__name__})")
    try:
        annual = summarize(yt.income_stmt)
    except Exception as exc:
        log.debug("annual financials failed", exc_info=True)
        warnings.append(f"Annual financials unavailable ({exc.__class__.__name__})")
    return quarterly, annual, warnings

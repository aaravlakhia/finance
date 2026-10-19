"""Ready-made stock lists for the market scanner.

These are well-known large companies, not an official index membership list
(index members change over time). Any symbol that no longer trades is skipped.
"""

INDIA_LARGE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "INFY.NS", "SBIN.NS",
    "ITC.NS", "HINDUNILVR.NS", "LT.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "AXISBANK.NS", "MARUTI.NS",
    "SUNPHARMA.NS", "HCLTECH.NS", "M&M.NS", "ULTRACEMCO.NS", "TITAN.NS", "NTPC.NS", "ONGC.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "POWERGRID.NS", "ASIANPAINT.NS", "WIPRO.NS", "NESTLEIND.NS",
    "BAJAJFINSV.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "COALINDIA.NS", "BAJAJ-AUTO.NS", "TECHM.NS",
    "GRASIM.NS", "HINDALCO.NS", "CIPLA.NS", "DRREDDY.NS", "EICHERMOT.NS", "APOLLOHOSP.NS", "BEL.NS",
    "TRENT.NS", "ETERNAL.NS", "SBILIFE.NS", "HDFCLIFE.NS", "SHRIRAMFIN.NS", "TATACONSUM.NS",
    "JIOFIN.NS", "DMART.NS", "HAL.NS", "DIVISLAB.NS",
]

US_LARGE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "V",
    "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV", "WMT", "NFLX", "BAC", "KO", "ORCL",
    "CRM", "AMD", "PEP", "CVX", "MRK", "ADBE", "TMO", "CSCO", "ACN", "MCD", "ABT", "LIN", "DIS",
    "WFC", "INTC", "QCOM", "IBM", "CAT", "GE", "TXN", "AMGN", "PFE", "UBER", "NKE", "BA",
]

UNIVERSES = {
    "India large caps (50)": INDIA_LARGE,
    "US large caps (50)": US_LARGE,
}

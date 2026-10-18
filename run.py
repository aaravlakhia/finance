"""The easy way to run stocklens: open this file in Spyder (or IDLE, VS Code,
PyCharm) and press Run (F5). No terminal needed.

1. Change SYMBOL below to the stock you want.
2. Press Run. The first run installs the packages it needs (a few minutes).
"""

SYMBOL = "AAPL"     # US: AAPL, MSFT, TSLA   India: INFY.NS, TCS.NS, RELIANCE.NS (NSE) or RELIANCE.BO (BSE)
PERIOD = "1y"       # 1mo, 3mo, 6mo, 1y, 2y, 5y
MODE = "report"     # "report"    = text report in the console + price chart in your browser
                    # "dashboard" = the full interactive dashboard in your browser
SHOW_CHART = True   # report mode: also open the price chart in your browser

# ---------------------------------------------------------------------------
# You don't need to change anything below this line.

import importlib
import importlib.util
import logging
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = {"yfinance": "yfinance", "pandas": "pandas", "requests": "requests"}
DASHBOARD = {"plotly": "plotly", "streamlit": "streamlit"}
PORT = 8501


def python_exe():
    exe = sys.executable
    # Spyder/IDLE on Windows can run under pythonw.exe, which can't run pip properly.
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    return exe


def ensure(packages):
    """Install any missing packages into the Python that Spyder is using."""
    missing = [pip_name for module, pip_name in packages.items() if importlib.util.find_spec(module) is None]
    if not missing:
        return True
    print(f"Installing {', '.join(missing)} (one-time, may take a few minutes)...")
    result = subprocess.run([python_exe(), "-m", "pip", "install", *missing], stdin=subprocess.DEVNULL)
    importlib.invalidate_caches()
    if result.returncode != 0:
        print("\nAutomatic install failed. Open 'Anaconda Prompt' from the Start menu, run:\n"
              f"    pip install {' '.join(missing)}\n"
              "and then press Run again.")
        return False
    return True


def report():
    from stocklens.cli import format_report
    from stocklens.report import NoPriceData, build

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # hide yfinance's internal retry messages
    print(f"Fetching {SYMBOL} (prices, financials, filings, news)... this takes 10-30 seconds.\n")
    try:
        r = build(SYMBOL, period=PERIOD)
    except (NoPriceData, ValueError) as exc:
        print(exc)
        return
    print(format_report(r, news_count=20))

    if SHOW_CHART and ensure({"plotly": "plotly"}):
        from stocklens.charts import price_chart

        fig = price_chart(r.prices, r.timeline, r.ticker.market, show_macd=True)
        fig.update_layout(title=dict(text=f"{r.name} ({r.ticker.yahoo})", x=0.01, y=0.98),
                          margin=dict(t=110), paper_bgcolor="white")
        path = Path(tempfile.gettempdir()) / f"stocklens_{r.ticker.yahoo}.html"
        fig.write_html(path, include_plotlyjs=True)
        webbrowser.open(path.as_uri())
        print(f"\nChart opened in your browser. If it didn't, open this file: {path}")


def dashboard():
    url = f"http://localhost:{PORT}"
    print("Starting the dashboard...")
    proc = subprocess.Popen(
        [python_exe(), "-m", "streamlit", "run", str(HERE / "app.py"), "--server.port", str(PORT),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=HERE, stdin=subprocess.DEVNULL)
    try:
        for _ in range(60):  # wait up to 30 s for the server to come up
            if proc.poll() is not None:
                print("The dashboard stopped unexpectedly. Try MODE = \"report\" instead.")
                return
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        webbrowser.open(url)
        print(f"Dashboard running at {url} (opened in your browser).")
        print("To stop it: click the red square (Stop) above the console, or restart the console.")
        while proc.poll() is None:  # not proc.wait(): on Windows that can't be interrupted by Stop
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping the dashboard.")
    finally:
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        print(f"stocklens needs Python 3.10 or newer; this is Python {sys.version.split()[0]}. "
              "Please update Anaconda / Python.")
    else:
        sys.path.insert(0, str(HERE))
        if ensure({**CORE, **DASHBOARD} if MODE == "dashboard" else CORE):
            dashboard() if MODE == "dashboard" else report()

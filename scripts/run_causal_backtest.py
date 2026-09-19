r"""Run the causal (left-to-right) LONG backtest for a period and cache per-day results.

    venv\Scripts\python.exe scripts\run_causal_backtest.py 2025
    venv\Scripts\python.exe scripts\run_causal_backtest.py 2026 --workers 8
The notebooks notebooks/06_causal_LONG_2025.ipynb / 07_causal_LONG_2026.ipynb read the same cache.
"""
import argparse, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtester.causal_engine import Config, run_period, trades_frame

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    end = date(a.year, 12, 31) if a.year < date.today().year else date.today()
    res = run_period(date(a.year, 1, 1), end, Config(), workers=a.workers)
    T = trades_frame(res)
    print(f"{a.year}: {len(res)} days, {len(T)} trades, net Rs {T.pnl_rs.sum():,.0f}" if len(T) else f"{a.year}: no trades")

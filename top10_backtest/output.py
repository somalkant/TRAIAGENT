"""
Output writers for the Top-10 backtest.

top10_trades.csv  — tidy/long format, source of truth, one row per executed trade.
top10_matrix.csv  — the day x strategy matrix view, DERIVED from top10_trades.csv
                     (not stored independently): 2 rows per calendar day
                     ({date}_LONG, {date}_SHORT), one column per strategy, each
                     cell a JSON string of that trade's full detail (or blank).
"""
from __future__ import annotations

import json

import pandas as pd

from config.settings import TRADE_LOG_DIR

TRADES_FILE = TRADE_LOG_DIR / "top10_trades.csv"
MATRIX_FILE = TRADE_LOG_DIR / "top10_matrix.csv"

COLUMNS = [
    "date", "side", "strategy", "symbol", "signal_time", "entry_price", "qty",
    "notional_rs", "stop", "target", "exit_time", "exit_price", "exit_reason",
    "result", "gross_pnl_rs", "total_cost_rs", "net_pnl_rs", "net_pnl_pct",
    "brokerage", "stt", "exchange", "sebi", "gst", "stamp", "slippage",
]

_CELL_FIELDS = [c for c in COLUMNS if c not in ("date", "side", "strategy")]


def append_trades(rows: list[dict]) -> None:
    if not rows:
        return
    TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=COLUMNS)
    header = not TRADES_FILE.exists()
    df.to_csv(TRADES_FILE, mode="a", header=header, index=False)


def build_matrix(strategy_names: list[str]) -> None:
    """Rebuild the wide day x strategy matrix from the tidy trades CSV."""
    if not TRADES_FILE.exists():
        return
    trades = pd.read_csv(TRADES_FILE)

    rows = []
    for (d, side), group in trades.groupby(["date", "side"]):
        row = {"row_id": f"{d}_{side}"}
        by_strategy = {r["strategy"]: r for _, r in group.iterrows()}
        for name in strategy_names:
            if name in by_strategy:
                cell = {k: by_strategy[name][k] for k in _CELL_FIELDS}
                row[name] = json.dumps(cell, default=str)
            else:
                row[name] = ""
        rows.append(row)

    matrix = pd.DataFrame(rows, columns=["row_id"] + strategy_names)
    TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(MATRIX_FILE, index=False)

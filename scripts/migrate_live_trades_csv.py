"""
One-time migration of data/trade_logs/live_paper_trades.csv to the canonical
30-column schema written by live/paper_logger.py since the execution-safety
update, fixing three data bugs found in the live/backtest divergence review:

  1. Mixed row widths (22/23/24 columns) — the header was written once on
     June 15 while the logger's schema later gained entry_time and
     strategy_entry, so pandas misaligns columns on a naive read.
  2. A duplicate exit (KIRLOSENG 2026-06-23 logged twice by a tick-callback
     race) double-counting a Rs -10,898 loss.
  3. A SHORT trade booked with LONG P&L math (PATANJALI 2026-06-22: recorded
     Rs -3,931, actually Rs +2,478) by old code that defaulted a missing
     direction key to LONG.

Direction is inferred from geometry (target > entry = LONG), P&L is recomputed
with the backtester cost model, and result labels are re-derived (EXACT_WIN
now requires positive net P&L). The original file is kept as a .bak copy.

Usage:
    python scripts/migrate_live_trades_csv.py             # migrate in place
    python scripts/migrate_live_trades_csv.py --dry-run   # report only
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import TRADE_LOG_DIR
from backtester.cost_model import net_pnl
from live.paper_logger import _COLUMNS, _result_label

LIVE_FILE = TRADE_LOG_DIR / "live_paper_trades.csv"

# Historical schemas, oldest first. Each maps a row width to its column order.
_SCHEMA_22 = ["date", "symbol", "signal_time", "entry_price", "quantity",
              "position_rs", "stop_loss", "target", "rr", "strategies_fired",
              "agreeing_count", "composite_score", "driver_strategy", "reason",
              "exit_time", "exit_price", "exit_reason", "result", "pnl_rs",
              "pnl_pct", "predicted_win_pct", "conviction_tier"]
_SCHEMA_23 = (_SCHEMA_22[:3] + ["entry_time"] + _SCHEMA_22[3:])
_SCHEMA_24 = (_SCHEMA_23[:4] + ["strategy_entry"] + _SCHEMA_23[4:])
# 30-col: execution-safety-layer schema before exit_fill_status was added
# 31-col: before the vol-sizing columns (atr_pct, size_cap_reason) were added
_SCHEMA_31 = [c for c in _COLUMNS if c not in ("atr_pct", "size_cap_reason")]
_SCHEMA_30 = [c for c in _SCHEMA_31 if c != "exit_fill_status"]
_SCHEMAS = {22: _SCHEMA_22, 23: _SCHEMA_23, 24: _SCHEMA_24,
            30: _SCHEMA_30, 31: _SCHEMA_31, len(_COLUMNS): _COLUMNS}

_NUMERIC = ["strategy_entry", "entry_price", "quantity", "position_rs", "stop_loss",
            "target", "rr", "agreeing_count", "composite_score", "exit_price",
            "pnl_rs", "pnl_pct", "predicted_win_pct", "entry_drift_pct",
            "signal_age_min", "overlap_ratio", "atr_pct"]


def load_mixed(path: Path) -> pd.DataFrame:
    rows = []
    with open(path, newline="") as f:
        raw = list(csv.reader(f))
    for i, row in enumerate(raw[1:], start=2):
        schema = _SCHEMAS.get(len(row))
        if schema is None:
            print(f"  line {i}: unknown row width {len(row)} — kept raw, please review")
            schema = _COLUMNS[:len(row)]
        d = dict(zip(schema, row))
        rows.append(d)
    df = pd.DataFrame(rows)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    for col in _NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[_COLUMNS]


def migrate(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes = []

    # 1. Dedupe exact double-logged exits
    before = len(df)
    df = df.drop_duplicates(
        subset=["date", "symbol", "entry_time", "entry_price", "exit_time", "exit_price"]
    ).reset_index(drop=True)
    if len(df) < before:
        notes.append(f"removed {before - len(df)} duplicate exit row(s)")

    # 2. Fill direction from geometry where missing (old rows never logged it)
    inferred = np.where(df["target"] > df["entry_price"], "LONG", "SHORT")
    missing_dir = (df["direction"] == "") | df["direction"].isna()
    if missing_dir.any():
        df.loc[missing_dir, "direction"] = inferred[missing_dir]
        notes.append(f"inferred direction for {int(missing_dir.sum())} row(s)")

    # 3. Recompute P&L with the correct direction sign
    fixed = 0
    for idx, r in df.iterrows():
        dirn = 1 if r["direction"] == "LONG" else -1
        true_pnl = net_pnl(float(r["entry_price"]), float(r["exit_price"]),
                           int(r["quantity"]), direction=dirn)
        if abs(true_pnl - float(r["pnl_rs"])) > 1.0:
            notes.append(f"P&L fixed: {r['date']} {r['symbol']} "
                         f"{r['pnl_rs']:,.0f} -> {true_pnl:,.0f}")
            fixed += 1
        df.at[idx, "pnl_rs"]  = round(true_pnl, 2)
        pos = float(r["entry_price"]) * int(r["quantity"])
        df.at[idx, "pnl_pct"] = round(true_pnl / pos * 100, 2) if pos else 0.0
        df.at[idx, "result"]  = _result_label(str(r["exit_reason"]), true_pnl)

    # 4. Defaults for instrumentation columns on pre-migration rows
    df["overlap_tier"]     = df["overlap_tier"].replace("", "N/A").fillna("N/A")
    df["profit_locked"]    = df["profit_locked"].replace("", "False").fillna("False")
    df["exit_fill_status"] = df["exit_fill_status"].replace("", "N/A").fillna("N/A")
    df["size_cap_reason"]  = df["size_cap_reason"].replace("", "N/A").fillna("N/A")
    for col in ["entry_drift_pct", "signal_age_min"]:
        df[col] = df[col].fillna(0.0)

    return df, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, don't write")
    args = ap.parse_args()

    if not LIVE_FILE.exists():
        print(f"Not found: {LIVE_FILE}")
        return

    df = load_mixed(LIVE_FILE)
    total_before = df["pnl_rs"].sum()
    df, notes = migrate(df)
    total_after = df["pnl_rs"].sum()

    print(f"{LIVE_FILE}")
    print(f"  rows: {len(df)} | total P&L: Rs {total_before:,.0f} -> Rs {total_after:,.0f}")
    for n in notes:
        print(f"  - {n}")

    if args.dry_run:
        print("  (dry run — nothing written)")
        return

    bak = LIVE_FILE.with_suffix(".csv.bak")
    shutil.copy2(LIVE_FILE, bak)
    df.to_csv(LIVE_FILE, index=False)
    print(f"  migrated in place — original backed up to {bak.name}")


if __name__ == "__main__":
    main()

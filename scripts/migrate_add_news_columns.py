"""
One-time migration: add the six news_* columns (Phase 2.7, monitor-only) to the
existing data/trade_logs/live_paper_trades.csv so its header matches the schema
now written by live/paper_logger.py._COLUMNS.

Without this, the logger appends 39-column rows under a 33-column header and
pandas misaligns every column on the next read. Historical rows (logged before
the news feature existed) get "not assessed" defaults:

    news_signal = "N/A"   news_source = "N/A"   news_headline = ""
    news_score / news_conf / news_count = blank

"N/A" is deliberately distinct from the live value "UNAVAILABLE" (which means
news WAS assessed at entry but the fetch/classify failed).

Idempotent: re-running when the columns already exist is a no-op. If the CSV
doesn't exist yet, there's nothing to migrate — the logger writes the full
header on first trade.

Usage:
    python scripts/migrate_add_news_columns.py             # migrate in place
    python scripts/migrate_add_news_columns.py --dry-run   # report only
"""
import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import TRADE_LOG_DIR
from live.paper_logger import _COLUMNS

LIVE_FILE = TRADE_LOG_DIR / "live_paper_trades.csv"

_NEWS_COLS = ["news_signal", "news_score", "news_conf",
              "news_headline", "news_count", "news_source"]
# "Not assessed" defaults for pre-existing rows; blank (NaN) for the numerics.
_DEFAULTS = {"news_signal": "N/A", "news_source": "N/A", "news_headline": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, don't write")
    args = ap.parse_args()

    if not LIVE_FILE.exists():
        print(f"Not found: {LIVE_FILE} — nothing to migrate "
              "(logger will write the full header on the first trade).")
        return

    df = pd.read_csv(LIVE_FILE)
    missing = [c for c in _NEWS_COLS if c not in df.columns]

    print(f"{LIVE_FILE}")
    print(f"  rows: {len(df)} | columns: {len(df.columns)}")

    if not missing:
        print("  already migrated — all news_* columns present. No change.")
        return

    for col in missing:
        df[col] = _DEFAULTS.get(col, pd.NA)
    print(f"  added {len(missing)} column(s): {', '.join(missing)}")

    # Reorder to the canonical schema; keep any unexpected extras at the end.
    ordered = [c for c in _COLUMNS if c in df.columns]
    extras = [c for c in df.columns if c not in _COLUMNS]
    if extras:
        print(f"  note: unexpected extra columns kept at end: {', '.join(extras)}")
    df = df[ordered + extras]

    if args.dry_run:
        print("  (dry run - nothing written)")
        return

    bak = LIVE_FILE.with_suffix(".csv.pre_news.bak")
    shutil.copy2(LIVE_FILE, bak)
    df.to_csv(LIVE_FILE, index=False)
    print(f"  migrated in place - original backed up to {bak.name}")


if __name__ == "__main__":
    main()

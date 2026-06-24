"""
Pre-Market Watchlist Builder — Stage 1 stock selector CLI.

Loads historical data up to the given date, runs liquidity + trend +
chart-pattern filters on all stocks, and prints the top N candidates
most likely to generate intraday signals that day.

Usage:
    python build_watchlist.py 2019-01-07
    python build_watchlist.py 2019-01-07 --size 30
    python build_watchlist.py 2019-01-07 --no-save

Output:
    Console table + checkpoints/watchlist_{date}.json (unless --no-save)

The saved JSON is automatically picked up by run_analysis.py / engine.py
when it runs the same trade_date — so building the watchlist first speeds
up the backtester significantly (500 → 25 stocks per day).
"""

import argparse
import logging
import sys
from datetime import date

from backtester.engine import _preload_data
from watchlist.pre_filter import PreMarketFilter, save_watchlist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build pre-market watchlist for a given trading date",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("date",     help="Trade date YYYY-MM-DD")
    parser.add_argument("--size",   type=int, default=25, help="Watchlist size (default: 25)")
    parser.add_argument("--no-save", action="store_true", help="Print only, do not write JSON")
    args = parser.parse_args()

    try:
        trade_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"[ERROR] Invalid date: {args.date} — use YYYY-MM-DD")
        sys.exit(1)

    log.info(f"Building watchlist for {trade_date} (size={args.size})...")

    all_data, _ = _preload_data(trade_date.year)
    if not all_data:
        log.error(f"No data loaded for {trade_date.year} — run the download notebook first")
        sys.exit(1)

    flt = PreMarketFilter()
    flt.WATCHLIST_SIZE = args.size
    watchlist = flt.build(trade_date, all_data)

    if not watchlist:
        log.warning("No stocks passed pre-market filter — check data coverage or try another date")
        sys.exit(0)

    _print_table(watchlist, trade_date)

    if not args.no_save:
        path = save_watchlist(watchlist, trade_date)
        print(f"  Saved → {path}\n")


def _print_table(watchlist: list[dict], trade_date: date) -> None:
    w = 72
    sep = "-" * w
    print(f"\n{sep}")
    print(f"  Pre-Market Watchlist -- {trade_date}   ({len(watchlist)} stocks selected)")
    print(sep)
    print(f"  {'#':<3}  {'Symbol':<16}  {'Score':>6}  {'Turnover':>10}  Active Signals")
    print(sep)
    for i, entry in enumerate(watchlist, 1):
        sig_names = ", ".join(s[0] for s in entry["signals"])
        print(
            f"  {i:<3}  {entry['symbol']:<16}  {entry['pre_score']:>6.1f}  "
            f"{entry['turnover_cr']:>8.1f} Cr  {sig_names}"
        )
    print(sep)

    # Score legend
    print(
        "\n  Score key: DAILY-BIAS=2.0  chart pattern=1.5 each  PDH-CLOSE=0.5\n"
        "  Max possible score: 2.0 + (4 x 1.5) + 0.5 = 8.5\n"
    )


if __name__ == "__main__":
    main()

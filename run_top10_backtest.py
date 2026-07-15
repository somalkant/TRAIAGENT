"""
Top-10 correlation-reduced strategy backtest, 2021-2026 — independent Rs 10L
capital per strategy (Rs 5L long / Rs 5L short), max 1 long + 1 short trade
per strategy per day. Separate from the main backtester/engine.py system.

Usage:
    python run_top10_backtest.py                                    # full 2021-01-01..2026-07-10 range
    python run_top10_backtest.py --start 2021-01-04 --end 2021-01-29 # smoke test window
    python run_top10_backtest.py --no-resume                        # ignore checkpoint, start fresh
    python run_top10_backtest.py --rebuild-matrix                   # re-derive the wide matrix only

Requires config/fno_symbols.csv to exist first — run scripts/build_fno_list.py once.
"""
import argparse
import logging
from datetime import date, datetime

from top10_backtest.engine import run
from top10_backtest.output import build_matrix
from top10_backtest.strategies import TOP10_NAMES


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=_parse_date, default=date(2021, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=date(2026, 7, 10))
    parser.add_argument("--no-resume", action="store_true", help="ignore checkpoint, start fresh")
    parser.add_argument("--rebuild-matrix", action="store_true",
                         help="only rebuild the wide matrix from the existing trades CSV")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")

    if args.rebuild_matrix:
        build_matrix(TOP10_NAMES)
        return

    run(args.start, args.end, resume=not args.no_resume)
    build_matrix(TOP10_NAMES)


if __name__ == "__main__":
    main()

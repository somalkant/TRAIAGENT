"""
Long/short universe filters for the Top-10 backtest.

LONG  — any NSE stock with >= Rs 300 Cr median 20-day turnover, computed from
        history strictly before trade_date (no look-ahead).
SHORT — restricted to the static F&O-eligible stock list (config/fno_symbols.csv),
        applied unchanged across the whole backtest window per user's choice.
        Run scripts/build_fno_list.py once to generate that file.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import pandas as pd

from config.settings import BASE_DIR

LONG_TURNOVER_MIN_CR = 300.0
FNO_LIST_FILE = BASE_DIR / "config" / "fno_symbols.csv"


def long_universe(all_data: dict[str, pd.DataFrame], trade_date: date,
                   threshold_cr: float = LONG_TURNOVER_MIN_CR) -> set[str]:
    """Symbols with >= threshold_cr median 20-day turnover, using only history before trade_date."""
    eligible = set()
    for symbol, df in all_data.items():
        recent = df[df["datetime"].dt.date < trade_date].tail(20 * 75)
        if recent.empty:
            continue
        daily_turnover = (recent["close"] * recent["volume"]).groupby(recent["datetime"].dt.date).sum()
        if daily_turnover.empty:
            continue
        if float(daily_turnover.median()) / 1e7 >= threshold_cr:
            eligible.add(symbol)
    return eligible


@lru_cache(maxsize=1)
def short_universe() -> frozenset[str]:
    """Static F&O-eligible stock list, loaded once from config/fno_symbols.csv."""
    if not FNO_LIST_FILE.exists():
        raise FileNotFoundError(
            f"{FNO_LIST_FILE} not found — run `python scripts/build_fno_list.py` first "
            "to fetch the current F&O stock list from your broker."
        )
    df = pd.read_csv(FNO_LIST_FILE)
    return frozenset(df["symbol"].astype(str).str.upper())

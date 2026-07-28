"""
Long/short universe filters for the Top-10 backtest.

LONG  — any NSE stock with >= Rs 300 Cr median 20-day turnover, computed from
        history strictly before trade_date (no look-ahead).
SHORT — the static F&O-eligible stock list (config/fno_symbols.csv) intersected
        with the SAME turnover floor as LONG. F&O eligibility alone is a
        structural/regulatory criterion, not a live-depth guarantee — the
        2026-07-15 live session showed a low-turnover F&O name (PATANJALI,
        ~82cr) with a real-time book that had moved ~3% away from the signal
        price within 10 minutes. Turnover isn't sufficient on its own either
        (a 365cr-turnover name still showed thin moment-to-moment depth that
        same day) — see live/top10_agent.py's pre-trade fill gate for the
        complementary fix that catches what a static threshold can't.
        Run scripts/build_fno_list.py once to generate the F&O list file.
"""
from __future__ import annotations

from datetime import date, time
from functools import lru_cache

import pandas as pd

from config.settings import BASE_DIR

LONG_TURNOVER_MIN_CR = 300.0
FNO_LIST_FILE = BASE_DIR / "config" / "fno_symbols.csv"

_LOOKBACK_DAYS  = 20
_SESSION_START  = time(9, 15)
_SESSION_END    = time(15, 25)   # last 5-min bar of a 09:15-15:30 session starts at 15:25
# Generous bar-count pre-filter before the precise date-based selection below — bounds
# the scan for performance on symbols with years of history. Real sessions run ~75
# bars/day; this comfortably covers _LOOKBACK_DAYS even if some days in between carry
# extra (e.g. stray post-close) bars that the session-hours filter will drop anyway.
_PREFILTER_BARS = 40 * 90


def long_universe(all_data: dict[str, pd.DataFrame], trade_date: date,
                   threshold_cr: float = LONG_TURNOVER_MIN_CR) -> set[str]:
    """
    Symbols with >= threshold_cr median 20-day turnover, using only history before
    trade_date. Selects by actual trading-day count, not raw bar count — a fixed
    `.tail(20 * 75)` bar slice silently drifts (fewer real days captured, inflated
    per-day turnover) if any day in the window ever carries more than the normal
    ~75 session bars, which happened for real in June 2026 (stray post-close bars
    doubled reported turnover on two dates and flipped LONG/SHORT eligibility for
    several stocks). Restricting to session hours before grouping by date makes
    this robust to that class of data glitch regardless of its cause.
    """
    eligible = set()
    for symbol, df in all_data.items():
        prior = df[df["datetime"].dt.date < trade_date].tail(_PREFILTER_BARS)
        if prior.empty:
            continue
        dt = prior["datetime"]
        session = prior[(dt.dt.time >= _SESSION_START) & (dt.dt.time <= _SESSION_END)]
        if session.empty:
            continue
        session_dates = session["datetime"].dt.date
        last_n_days = sorted(session_dates.unique())[-_LOOKBACK_DAYS:]
        recent = session[session_dates.isin(last_n_days)]
        daily_turnover = (recent["close"] * recent["volume"]).groupby(recent["datetime"].dt.date).sum()
        if daily_turnover.empty:
            continue
        if float(daily_turnover.median()) / 1e7 >= threshold_cr:
            eligible.add(symbol)
    return eligible


@lru_cache(maxsize=1)
def _load_fno_list() -> frozenset[str]:
    """Static F&O-eligible stock list, loaded once from config/fno_symbols.csv."""
    if not FNO_LIST_FILE.exists():
        raise FileNotFoundError(
            f"{FNO_LIST_FILE} not found — run `python scripts/build_fno_list.py` first "
            "to fetch the current F&O stock list from your broker."
        )
    df = pd.read_csv(FNO_LIST_FILE)
    return frozenset(df["symbol"].astype(str).str.upper())


def short_universe(all_data: dict[str, pd.DataFrame], trade_date: date,
                    threshold_cr: float = LONG_TURNOVER_MIN_CR) -> set[str]:
    """F&O-eligible stocks that ALSO clear the same turnover floor as LONG."""
    fno = _load_fno_list()
    turnover_ok = long_universe(all_data, trade_date, threshold_cr)
    return fno & turnover_ok

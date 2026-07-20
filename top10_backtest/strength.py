"""
Move-strength classification — a purely observational STRONG/MEDIUM/LOW tag
computed at the exact moment a signal fires, before the trade is placed.

Does NOT influence sizing, entry, or exit in any way. It exists to build a
track record so a future decision (e.g. sizing or filtering by conviction)
can be made on real evidence instead of a guess.

Designed from two independent consultations plus a codebase check:
  - Intraday-trading read: relative volume vs. the SAME time-of-day history
    (not a flat daily average — volume is structurally U-shaped through the
    session), range expansion vs. trailing same-time-of-day true range, and
    close-location-value (where price settled within its own bar, in the
    trade's direction) are the three legs a trader actually trusts.
  - Statistics read: fixed absolute thresholds don't generalize across a
    universe of stocks with very different liquidity/volatility, and raw
    z-scores are unstable on short, heavy-tailed samples. Convert each raw
    feature to an expanding-window PERCENTILE RANK against its own trailing
    history instead, take the MEDIAN of the per-feature percentiles as one
    robust composite in [0,1], and gate on minimum history length so a
    cold-start read isn't presented with false confidence.

Pure function, no I/O, no shared state — safe to call identically from a
day-by-day backtest loop or a live streaming loop, PROVIDED the caller passes
data no more advanced than the signal bar. See _truncate_to_signal_bar: this
module never trusts that `today_5min` is already limited to "so far" — the
backtest's own _get_today() hands strategies the WHOLE day's bars (individual
strategies self-truncate internally by scanning chronologically), while
live's LiveDataManager.get_today() naturally only contains bars up to now.
Reading the raw last row of `today_5min` would be correct in live today and
silently wrong the moment this is ever reused in the backtest.
"""
from __future__ import annotations

import pandas as pd

LOOKBACK_DAYS    = 20   # how many past same-time-of-day bars to gather at most
MIN_HISTORY_DAYS = 15   # below this many matching historical bars, return UNRATED

_STRONG_CUTOFF = 0.70
_MEDIUM_CUTOFF = 0.35


def classify_strength(direction: int, today_5min: pd.DataFrame, history_5min: pd.DataFrame,
                       signal_time: str) -> str:
    """
    Returns "STRONG" / "MEDIUM" / "LOW" / "UNRATED".

    direction     : +1 for LONG, -1 for SHORT — determines which side of the
                     bar counts as "in the trade's favor" for close-location.
    today_5min    : today's 5-min OHLCV bars (may include bars after the
                     signal — this function truncates itself, see module doc).
    history_5min  : all prior trading days' 5-min OHLCV bars (strictly before
                     today — no same-day rows).
    signal_time   : the signal bar's "HH:MM" label (Signal.signal_time).
    """
    if not signal_time or today_5min is None or today_5min.empty:
        return "UNRATED"

    today = _truncate_to_signal_bar(today_5min, signal_time)
    if today.empty:
        return "UNRATED"
    bar = today.iloc[-1]

    reference = _same_time_reference(history_5min, signal_time)
    if len(reference) < MIN_HISTORY_DAYS:
        return "UNRATED"

    prev_close = today.iloc[-2]["close"] if len(today) >= 2 else None
    ref_prev_closes = _reference_prev_closes(history_5min, reference)

    vol_pctile   = _percentile_rank(bar["volume"], reference["volume"].to_numpy())
    range_pctile = _percentile_rank(
        _true_range(bar, prev_close),
        [_true_range(row, ref_prev_closes[i]) for i, (_, row) in enumerate(reference.iterrows())],
    )
    clv = _close_location_value(bar, direction)

    composite = _median([vol_pctile, range_pctile, clv])

    if composite >= _STRONG_CUTOFF:
        return "STRONG"
    if composite >= _MEDIUM_CUTOFF:
        return "MEDIUM"
    return "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Feature helpers
# ─────────────────────────────────────────────────────────────────────────────

def _truncate_to_signal_bar(today_5min: pd.DataFrame, signal_time: str) -> pd.DataFrame:
    """Drops any bar labeled after signal_time — mandatory no-lookahead guard,
    see module docstring. Assumes datetime-sortable input; re-sorts defensively."""
    df = today_5min.sort_values("datetime")
    labels = df["datetime"].dt.strftime("%H:%M")
    return df[labels <= signal_time]


def _same_time_reference(history_5min: pd.DataFrame, signal_time: str) -> pd.DataFrame:
    """Up to the most recent LOOKBACK_DAYS bars from prior days at the same
    HH:MM label as the signal bar."""
    if history_5min is None or history_5min.empty:
        return history_5min.iloc[0:0] if history_5min is not None else pd.DataFrame()
    labels = history_5min["datetime"].dt.strftime("%H:%M")
    same_time = history_5min[labels == signal_time].sort_values("datetime")
    return same_time.tail(LOOKBACK_DAYS)


def _reference_prev_closes(history_5min: pd.DataFrame, reference: pd.DataFrame) -> list:
    """For each reference bar, the close of the bar immediately preceding it
    that same day (None if the reference bar is that day's first)."""
    out = []
    for dt in reference["datetime"]:
        same_day = history_5min[history_5min["datetime"].dt.date == dt.date()]
        same_day = same_day[same_day["datetime"] < dt].sort_values("datetime")
        out.append(same_day.iloc[-1]["close"] if not same_day.empty else None)
    return out


def _true_range(bar, prev_close) -> float:
    high, low = bar["high"], bar["low"]
    if prev_close is None:
        return float(high - low)
    return float(max(high - low, abs(high - prev_close), abs(low - prev_close)))


def _percentile_rank(value: float, reference_values) -> float:
    """Fraction of the reference distribution at or below `value`. Empty
    reference defaults to a neutral 0.5 (should be pre-empted by the
    MIN_HISTORY_DAYS gate, but kept safe here regardless)."""
    ref = [v for v in reference_values if v is not None]
    if not ref:
        return 0.5
    return sum(1 for v in ref if v <= value) / len(ref)


def _close_location_value(bar, direction: int) -> float:
    """Where price settled within its own bar, in the trade's favor.
    LONG: close near the high is favorable. SHORT: close near the low is
    favorable. Bounded in [0,1] by construction — used directly, no
    reference distribution needed."""
    high, low, close = bar["high"], bar["low"], bar["close"]
    bar_range = high - low
    if bar_range <= 0:
        return 0.5
    if direction == 1:
        return float((close - low) / bar_range)
    return float((high - close) / bar_range)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2

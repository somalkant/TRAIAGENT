"""
Pullback entry filter (#4) — don't chase the extended signal bar; wait for a
retest and enter at a better price, or skip.

Rationale (from the 10-session live review): the observational move-strength tag
showed STRONG-tagged entries — high relative volume, wide range, close at the
extreme — performed the WORST (avg -0.57% vs LOW's -0.17%). That is the
signature of chasing: by the time a bar looks maximally convincing, the move is
extended and the entry is at the top of the impulse (for breakouts) or against a
genuine trend (for reversions), right before the pullback that taps the stop.

The fix is entry *location*, not the entry *signal*: after a strategy fires,
require price to retrace a fraction of the entry->stop distance back toward the
stop (a pullback) within a few bars, and enter there. Benefits: a better fill,
and a tighter, better-located stop (same structural stop level, smaller
entry->stop distance => larger realized reward:risk). If the pullback never
comes, the trade is skipped — which is exactly the anti-chasing benefit: no
entry at the top of a move that ran away without you.

`pullback_level()` is shared by both engines. `apply_pullback()` does the
full-day backtest scan (it can see the bars after the signal); the live agent
uses `pullback_level()` with its own bar-by-bar pending-signal check, since it
cannot see future bars.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import time as dtime

import pandas as pd


def pullback_level(entry: float, stop: float, direction: int, fraction: float) -> float:
    """Price a `fraction` of the way from entry back toward the stop.
    LONG (dir +1): below entry. SHORT (dir -1): above entry. Always strictly
    between entry and stop, so it preserves signal validity (still on the right
    side of both stop and target)."""
    return entry - direction * fraction * abs(entry - stop)


def apply_pullback(signal, today_5min: pd.DataFrame, fraction: float, max_bars: int):
    """
    Backtest-side transform. Returns an adjusted Signal (entered at the pullback
    price, signal_time moved to the retest bar) if price retraces to the
    pullback level within `max_bars` bars after the signal bar — else None
    (skip the trade, the pullback never arrived).

    Keeps the original structural stop and target; only the entry price and the
    signal_time (used by the outcome simulator as the "enter after this bar"
    marker) change.
    """
    sig_t = _parse_time(signal.signal_time)
    if sig_t is None:
        return None

    df = today_5min.sort_values("datetime")
    after = df[df["datetime"].dt.time > sig_t].head(max_bars)
    if after.empty:
        return None

    level = pullback_level(signal.entry, signal.stop, signal.direction, fraction)

    for _, bar in after.iterrows():
        reached = (bar["low"] <= level) if signal.direction == 1 else (bar["high"] >= level)
        if reached:
            bar_time = pd.Timestamp(bar["datetime"]).strftime("%H:%M")
            rr = _reward_risk(level, signal.target, signal.stop, signal.direction)
            return replace(signal, entry=round(level, 2), signal_time=bar_time, rr=rr)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_time(signal_time: str) -> dtime | None:
    if not signal_time:
        return None
    try:
        h, m = map(int, str(signal_time).split(":"))
        return dtime(h, m)
    except Exception:
        return None


def _reward_risk(entry: float, target: float, stop: float, direction: int) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    reward = (target - entry) if direction == 1 else (entry - target)
    return round(reward / risk, 2)

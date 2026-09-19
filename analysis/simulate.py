"""
LONG trade simulation on 5-min bars, with switchable entry and exit rules.

Conventions (chosen to be honest, not flattering):
  * Exits are checked from the bar AFTER the entry bar (the entry happens mid-bar).
  * A bar that touches both stop and target is scored as a STOP (the backtest does the opposite).
  * A stop that gaps (bar opens below it) fills at the open, not at the stop.
  * Square-off: the 14:45 bar's close, i.e. the 2:50 PM price live uses.
  * Costs: backtester.cost_model.net_pnl (brokerage, STT, exchange, GST, stamp, 0.05%/side slippage).
  * Trailing profit-lock = live's rule: once the best price is +TRIGGER% above entry, the stop
    trails TRAIL% below that best price and only ratchets up; the fixed target is then dropped
    (ride past target). The trail uses completed bars' highs (it tightens from the next bar).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from backtester.cost_model import net_pnl
from analysis.replay import load_symbol

SQUAREOFF = 14 * 60 + 45          # label of the bar whose close is the 2:50 PM exit


CACHE_START, CACHE_END = date(2024, 10, 1), date(2026, 12, 31)


@lru_cache(maxsize=None)
def _symbol_frame(symbol: str) -> pd.DataFrame:
    """Whole cached period for one symbol, loaded once (sorted, naive IST, day ordinal in _d)."""
    df = load_symbol(symbol, CACHE_START, CACHE_END)
    if not df.empty:
        df["m"] = df.datetime.dt.hour * 60 + df.datetime.dt.minute
    return df


def day_bars(symbol: str, d: date) -> pd.DataFrame:
    df = _symbol_frame(symbol)
    if df.empty:
        return df
    o = d.toordinal()
    lo, hi = df._d.searchsorted(o, "left"), df._d.searchsorted(o, "right")
    return df.iloc[lo:hi].drop(columns="_d").reset_index(drop=True)


def bar_index(bars: pd.DataFrame, hhmm: str) -> int | None:
    h, m = map(int, hhmm.split(":")[:2])
    idx = np.flatnonzero(bars.m.values == h * 60 + m)
    return int(idx[0]) if len(idx) else None


@dataclass
class Exit:
    price: float
    time: str
    reason: str
    mfe_pct: float
    mae_pct: float


def run_exit(bars: pd.DataFrame, entry_idx: int, entry: float, stop: float, target: float | None,
             trail: bool = False, trigger_pct: float = 1.0, trail_pct: float = 0.5,
             ride_past_target: bool = True, ambiguous: str = "stop",
             squareoff: int = SQUAREOFF, start_next_bar: bool = True,
             gap_fill: bool = True, time_exit_at: str = "close") -> Exit:
    """gap_fill=False / time_exit_at='open' + squareoff=15:15 reproduce backtester.engine._simulate_outcome."""
    cur_stop, peak, trough, locked = stop, entry, entry, False
    lo_i = entry_idx + 1 if start_next_bar else entry_idx
    M, O, H, Lo, C = (bars.m.values, bars.open.values, bars.high.values, bars.low.values, bars.close.values)
    hm = lambda m: f"{int(m) // 60:02d}:{int(m) % 60:02d}"
    for i in range(lo_i, len(M)):
        if M[i] > squareoff:
            break
        if time_exit_at == "open" and M[i] == squareoff:
            return Exit(float(O[i]), hm(M[i]), "TIME_EXIT", (peak - entry) / entry * 100, (trough - entry) / entry * 100)
        hit_s = Lo[i] <= cur_stop
        tgt_live = target is not None and not (ride_past_target and locked)
        hit_t = tgt_live and H[i] >= target
        if hit_s and hit_t:
            if ambiguous == "stop":
                hit_t = False
            else:
                hit_s = False
        if hit_s:
            px = min(cur_stop, float(O[i])) if gap_fill else cur_stop
            return Exit(px, hm(M[i]), "PROFIT_LOCK_STOP" if locked else "STOP_HIT",
                        (peak - entry) / entry * 100, (min(trough, px) - entry) / entry * 100)
        if hit_t:
            return Exit(float(target), hm(M[i]), "TARGET_HIT",
                        (max(peak, target) - entry) / entry * 100, (trough - entry) / entry * 100)
        peak, trough = max(peak, float(H[i])), min(trough, float(Lo[i]))
        if trail and (peak - entry) / entry * 100 >= trigger_pct:
            locked = True
            cur_stop = max(cur_stop, round(peak * (1 - trail_pct / 100), 2))
    k = np.flatnonzero(M <= squareoff)
    j = int(k[-1]) if len(k) else len(M) - 1
    return Exit(float(C[j]), hm(M[j]), "TIME_EXIT", (peak - entry) / entry * 100, (trough - entry) / entry * 100)


def limit_fill(bars: pd.DataFrame, from_idx: int, limit: float, window_bars: int) -> tuple[int, float] | None:
    """Buy limit resting from bar `from_idx`: filled on the first bar whose low <= limit, at the
    limit (or at the open if the bar opens below it). None if it never fills in the window."""
    for i in range(from_idx, min(len(bars), from_idx + window_bars)):
        b = bars.iloc[i]
        if b.m > SQUAREOFF:
            break
        if b.low <= limit:
            return i, min(limit, float(b.open))
    return None


def pnl(entry: float, exit_px: float, notional: float = 200_000, shares: int | None = None) -> tuple[float, int]:
    q = shares if shares is not None else int(notional // entry)
    if q <= 0:
        return 0.0, 0
    return float(net_pnl(entry, exit_px, q, direction=1)), q

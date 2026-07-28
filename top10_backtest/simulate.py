"""
Top-10 outcome simulator (#5) — the target/stop/15:15 bar-scan, plus an
optional mid-session time-stop.

This mirrors backtester.engine._simulate_outcome exactly (target checked before
stop each bar, 15:15 force-exit at that bar's open, running close otherwise) so
that with the time-stop DISABLED it is byte-for-byte identical to the proven
shared mechanic. It is a separate copy — rather than an edit to the shared
_simulate_outcome — because that function is also used by the old 38-strategy
system, which must not change.

The added rule: if a position hasn't reached at least TOP10_TIMESTOP_MIN_R "R"
of favourable excursion by TOP10_TIMESTOP_BARS bars after entry, it is flattened
at that bar's close (exit_reason "TIME_STOP"). R = entry-to-stop distance. This
is a capital-velocity / variance control — the live review found 44% of trades
drifting to the 15:15 square-off near breakeven (a coin flip), tying up capital
and a risk slot that a working trade could use. Target/stop hits on the
checkpoint bar itself take precedence over the time-stop.
"""
from __future__ import annotations

from datetime import time as dtime

import pandas as pd


def simulate_outcome_top10(signal, today_5min: pd.DataFrame, *,
                           timestop_enabled: bool = False,
                           timestop_bars: int = 12,
                           timestop_min_r: float = 0.5) -> dict:
    entry  = signal.entry
    target = signal.target
    stop   = signal.stop
    dirn   = signal.direction
    risk   = abs(entry - stop)

    sig_time = signal.signal_time or "09:15"
    try:
        h, m   = map(int, sig_time.split(":"))
        sig_dt = dtime(h, m)
    except Exception:
        sig_dt = dtime(9, 15)

    exit_dt     = dtime(15, 15)
    exit_price  = entry
    exit_reason = "TIME_EXIT"
    exit_time   = "15:15"

    bars_since_entry = 0
    for _, c in today_5min.iterrows():
        t = pd.Timestamp(c["datetime"]).time()
        if t <= sig_dt:
            continue
        if t >= exit_dt:
            exit_price  = float(c["open"])
            exit_reason = "TIME_EXIT"
            exit_time   = t.strftime("%H:%M")
            break

        bars_since_entry += 1

        if dirn == 1:
            if c["high"] >= target:
                exit_price, exit_reason, exit_time = target, "TARGET_HIT", t.strftime("%H:%M")
                break
            if c["low"] <= stop:
                exit_price, exit_reason, exit_time = stop, "STOP_HIT", t.strftime("%H:%M")
                break
            exit_price = float(c["close"])
            exit_time  = t.strftime("%H:%M")

        elif dirn == -1:
            if c["low"] <= target:
                exit_price, exit_reason, exit_time = target, "TARGET_HIT", t.strftime("%H:%M")
                break
            if c["high"] >= stop:
                exit_price, exit_reason, exit_time = stop, "STOP_HIT", t.strftime("%H:%M")
                break
            exit_price = float(c["close"])
            exit_time  = t.strftime("%H:%M")

        if timestop_enabled and risk > 0 and bars_since_entry >= timestop_bars:
            favorable = (exit_price - entry) if dirn == 1 else (entry - exit_price)
            if favorable < timestop_min_r * risk:
                exit_reason = "TIME_STOP"
                break

    return {"exit_price": exit_price, "exit_reason": exit_reason, "exit_time": exit_time}

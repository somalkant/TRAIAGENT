"""
Gap decomposition: from the backtest's reported LONG result to what live can actually do,
removing one piece of hindsight / optimism at a time, all priced at the same notional.

  W0  Backtest as reported      backtest pick, entry at the strategy level on the signal bar,
                                target-before-stop, stops fill at the level through gaps, 15:15 exit
  W1  + honest exits            same trades; stop-first on ambiguous bars, gap fills, 14:50 exit
  W2  + honest entry price      same stocks; enter at the price after the signal bar closes and the
                                scan decides (signal+5 min scan, bar-mid) instead of at the level
  W3  + no hindsight in picking causal replay: the first stock that passes the SAME quality filters
                                using only bars closed so far (votes, driver, time gates as of then)
  W4  + live's own gates        live's actual pick rule (30-min expiry, 0.30% drift gate, RR re-check,
                                stop viability) — what live would take on these days
  W5  + live's exit policy      W4 trades with live exits (stop capped at 1%, +1%/0.5% trailing lock)
Each step changes exactly one thing relative to the previous one.
"""
from __future__ import annotations

import pandas as pd

from analysis.policies import (bt_trades, trades_from_rows, pick_first_pass, pick_live, summarize,
                               BT_EXIT, REAL_BT_EXIT, LIVE_EXIT)


def waterfall(bt: pd.DataFrame, cand: pd.DataFrame, notional: float = 200_000) -> tuple[pd.DataFrame, dict]:
    steps = {
        "W0 backtest as reported": bt_trades(bt, "bt_level", BT_EXIT, notional),
        "W1 + honest exits": bt_trades(bt, "bt_level", REAL_BT_EXIT, notional),
        "W2 + honest entry price": bt_trades(bt, "market", REAL_BT_EXIT, notional),
        "W3 + no hindsight in picking": trades_from_rows(pick_first_pass(cand), "market", REAL_BT_EXIT, notional),
        "W4 + live's own gates": trades_from_rows(pick_live(cand), "market", REAL_BT_EXIT, notional),
        "W5 + live's exit policy": trades_from_rows(pick_live(cand), "market", LIVE_EXIT, notional),
    }
    rows = [summarize(t, k) for k, t in steps.items()]
    return pd.DataFrame(rows), steps

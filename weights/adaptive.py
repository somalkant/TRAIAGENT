"""Adaptive weight recalculation — runs every 20 trading days.

Phase 2B: weights are now {"long": float, "short": float} per strategy.
  - weight_long  updated from +1 trade outcomes (perf_long dict)
  - weight_short updated from -1 trade outcomes (perf_short dict)
  Both are updated independently.

Backward compat: if current_weights contains plain floats (old format),
they are migrated to {"long": v, "short": 1.0} on first update.
"""
from config.settings import (MIN_WEIGHT, MAX_WEIGHT, WEIGHT_MULTIPLIERS,
                              WIN_RATE_BOOST, WIN_RATE_HOLD_LOW, WIN_RATE_REDUCE,
                              REVIVAL_WEIGHT, WEIGHT_SIGNAL_WINDOW,
                              MIN_TRADES_FOR_WEIGHT_UPDATE)
import logging

log = logging.getLogger(__name__)


def _apply_update(old_w: float, win_rate: float) -> tuple[float, str]:
    if win_rate > WIN_RATE_BOOST:
        mult, action = WEIGHT_MULTIPLIERS["boost"],    "boost"
    elif win_rate > WIN_RATE_HOLD_LOW:
        mult, action = WEIGHT_MULTIPLIERS["hold"],     "hold"
    elif win_rate > WIN_RATE_REDUCE:
        mult, action = WEIGHT_MULTIPLIERS["reduce"],   "reduce"
    else:
        mult, action = WEIGHT_MULTIPLIERS["suppress"], "suppress"

    new_w = max(MIN_WEIGHT, min(MAX_WEIGHT, old_w * mult))

    if old_w <= MIN_WEIGHT and new_w <= MIN_WEIGHT:
        new_w  = REVIVAL_WEIGHT
        action = "revive"

    return round(new_w, 4), action


def _ensure_dict(w) -> dict:
    """Convert a plain float weight to the Phase 2B dict format."""
    if isinstance(w, dict):
        return w
    return {"long": float(w), "short": 1.0}


def update_weights(
    current_weights: dict,
    performance_long: dict[str, list],   # {strategy_name: [1,0,...]}  from +1 trades
    performance_short: dict[str, list],  # {strategy_name: [1,0,...]}  from -1 trades
    vix: float = 15.0,
) -> dict:
    """
    Recalculate weights based on recent trade outcomes.
    weight_long  ← updated from performance_long outcomes
    weight_short ← updated from performance_short outcomes
    Returns updated weights dict (all values as {"long": x, "short": y}).
    """
    new_weights = {k: _ensure_dict(v) for k, v in current_weights.items()}

    for name, outcomes in performance_long.items():
        if not outcomes:
            continue
        recent   = outcomes[-WEIGHT_SIGNAL_WINDOW:]
        if len(recent) < MIN_TRADES_FOR_WEIGHT_UPDATE:
            log.debug(f"  {name:<18} long  skipped — only {len(recent)} trades in window (min {MIN_TRADES_FOR_WEIGHT_UPDATE})")
            continue
        win_rate = sum(recent) / len(recent)
        w        = new_weights.get(name, {"long": 1.0, "short": 1.0})
        old_wl         = w.get("long", 1.0)
        new_wl, action = _apply_update(old_wl, win_rate)
        new_weights[name] = {**w, "long": new_wl}
        if abs(new_wl - old_wl) > 0.05:
            log.info(f"  {name:<18} long  {old_wl:.2f} -> {new_wl:.2f}  ({action}, wr={win_rate:.0%})")

    for name, outcomes in performance_short.items():
        if not outcomes:
            continue
        recent   = outcomes[-WEIGHT_SIGNAL_WINDOW:]
        if len(recent) < MIN_TRADES_FOR_WEIGHT_UPDATE:
            log.debug(f"  {name:<18} short skipped — only {len(recent)} trades in window (min {MIN_TRADES_FOR_WEIGHT_UPDATE})")
            continue
        win_rate = sum(recent) / len(recent)
        w        = new_weights.get(name, {"long": 1.0, "short": 1.0})
        old_ws         = w.get("short", 1.0)
        new_ws, action = _apply_update(old_ws, win_rate)
        new_weights[name] = {**w, "short": new_ws}
        if abs(new_ws - old_ws) > 0.05:
            log.info(f"  {name:<18} short {old_ws:.2f} -> {new_ws:.2f}  ({action}, wr={win_rate:.0%})")

    return new_weights

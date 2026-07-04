"""
Profit-lock exit policy — conservative early profit booking for live paper trading.

LONG trades only. If the strategy's calculated target is >= PROFIT_LOCK_MIN_TARGET_PCT
away from entry, cap the exit at a flat PROFIT_LOCK_CAP_PCT gain from entry instead of
waiting for the full (larger) target. Stop-loss is unchanged. SHORT trades are not
affected by this policy at all.
"""

from config.settings import PROFIT_LOCK_MIN_TARGET_PCT, PROFIT_LOCK_CAP_PCT


def evaluate_profit_lock(rec: dict, last_price: float) -> tuple[bool, float | None]:
    """
    Check whether an open LONG position should be exited under the profit-lock
    policy. Returns (should_exit, exit_price). exit_price is last_price (a
    market fill).
    """
    if rec.get("direction", "LONG") != "LONG":
        return False, None

    sig    = rec["signal"]
    entry  = float(sig["entry"])
    target = float(sig["target"])

    target_dist = target - entry
    if entry <= 0 or target_dist <= 0:
        return False, None

    target_pct = target_dist / entry * 100
    if target_pct < PROFIT_LOCK_MIN_TARGET_PCT:
        return False, None   # target move too small — policy doesn't apply

    cap_price = entry * (1 + PROFIT_LOCK_CAP_PCT / 100)
    if last_price >= cap_price:
        return True, last_price

    return False, None

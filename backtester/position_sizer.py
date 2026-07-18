"""Position sizing: min(notional cap, base_risk × conviction_mult / stop_pct[, ATR budget])."""
from config.settings import MAX_POSITION_SIZE, MAX_LOSS_PER_TRADE


def position_size(entry: float, stop: float, conviction_mult: float = 1.0,
                  atr_pct: float | None = None,
                  atr_risk_rs: float | None = None,
                  max_notional: float | None = None) -> tuple[float, int]:
    """
    Returns (rupee_size, shares).
    conviction_mult scales base risk up for high-confidence driver strategies:
      1.0 = STANDARD (Rs 20k risk)
      1.5 = MEDIUM   (Rs 30k risk)
      2.0 = HIGH     (Rs 40k risk)

    Optional volatility overlay (live only — backtester calls omit these args
    and get the exact historical behavior):
      atr_pct + atr_risk_rs : add a third cap atr_risk_rs / ATR% so every
        position moves roughly the same rupees on an average day, regardless
        of how tight the strategy's stop happens to be.
      max_notional : override the MAX_POSITION_SIZE cap (used to actually
        halve short exposure — scaling risk alone does nothing when the
        notional cap is what binds).
    """
    if entry <= 0 or stop <= 0 or entry == stop:
        return 0.0, 0
    stop_pct  = abs(entry - stop) / entry
    if stop_pct == 0:
        return 0.0, 0
    base_risk = MAX_LOSS_PER_TRADE * conviction_mult
    risk_size = base_risk / stop_pct
    cap       = max_notional if max_notional is not None else MAX_POSITION_SIZE
    rs_value  = min(cap, risk_size)
    if atr_pct and atr_pct > 0 and atr_risk_rs:
        rs_value = min(rs_value, atr_risk_rs / (atr_pct / 100))
    shares    = max(1, int(rs_value / entry))
    return round(shares * entry, 2), shares

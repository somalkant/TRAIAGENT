"""
All quality filters — ALL must pass for a recommendation.

Filters 1-7: apply to both LONG and SHORT signals.
Filters 8-10: short-specific only (skipped for LONG direction).

Thresholds are imported from config.settings so changing a constant there
automatically changes filter behaviour everywhere.
"""
from datetime import time
from strategies.base import Signal
from config.settings import (MIN_RISK_REWARD, MIN_STRATEGIES_AGREEING,
                              LIQUIDITY_MIN_TURNOVER, LOWER_CIRCUIT_BUFFER,
                              WEEK52_LOW_BUFFER, NIFTY_GREEN_THRESHOLD,
                              CORP_EVENT_MOVE_PCT)

_LIQUIDITY_CR = LIQUIDITY_MIN_TURNOVER / 1e7   # convert Rs to Crores
import pandas as pd

CIRCUIT_LIMIT = 0.10   # 10% move = assume circuit


def passes_all_filters(
    signal: Signal,
    today_5min: pd.DataFrame,
    daily_turnover_crore: float,
    strategies_agreeing: int,
    composite_score: float = 0.0,
    predicted_win_pct: float = 50.0,
    # Short-specific inputs (optional — ignored for LONG signals)
    week52_low: float = 0.0,
    nifty_pct_change: float = 0.0,
    recent_3day_move: float = 0.0,   # abs % move of stock in prior 3 days
) -> tuple[bool, str]:
    """Returns (passes, reason_if_failed)."""

    direction = signal.direction   # +1 or -1

    # ── Filters 1-7: apply to BOTH directions ────────────────────────────────

    # 1. Liquidity
    if daily_turnover_crore < _LIQUIDITY_CR:
        return False, f"Liquidity: turnover={daily_turnover_crore:.1f} Cr < {_LIQUIDITY_CR:.0f} Cr"

    # 2. Risk:Reward >= MIN_RISK_REWARD — bad low-RR drivers blocked via DRIVER_BLOCKED
    if signal.rr < MIN_RISK_REWARD:
        return False, f"RR={signal.rr:.2f} < {MIN_RISK_REWARD}"

    # 3. Agreement count — MIN raised to 4 (2025 Finding 5: 2-agreement was 32.3% win)
    if strategies_agreeing < MIN_STRATEGIES_AGREEING:
        return False, f"Only {strategies_agreeing} strategy agreed (need {MIN_STRATEGIES_AGREEING})"

    # 4. Not in circuit (both upper and lower circuit check)
    if not today_5min.empty and len(today_5min) > 1:
        open_p = float(today_5min.iloc[0]["open"])
        last_p = float(today_5min.iloc[-1]["close"])
        if open_p > 0 and abs(last_p - open_p) / open_p > CIRCUIT_LIMIT:
            return False, "Stock may be in circuit limit"

    # 6. Time gate — tiered thresholds (2025 Finding 10: 9:30 slot 3-year confirmed trap)
    if signal.signal_time:
        try:
            h, m  = map(int, signal.signal_time.split(":"))
            sig_t = time(h, m)

            if sig_t >= time(14, 0):
                return False, f"Signal at {signal.signal_time} — after 2:00 PM cutoff"

            # After 10:30 AM: skip unless outstanding (score >= 7)
            if sig_t >= time(10, 30) and composite_score < 7.0:
                return False, (f"After 10:30 AM requires score >= 7 "
                               f"(got {composite_score:.2f})")

            # 9:30-10:30 AM window: requires score >= 6 AND 5+ agreeing strategies
            if sig_t >= time(9, 30) and (composite_score < 6.0 or strategies_agreeing < 5):
                return False, (f"Signal at {signal.signal_time} requires score >= 6 and 5+ agreements "
                               f"(got score={composite_score:.2f}, agreeing={strategies_agreeing})")
        except Exception:
            pass

    # 7. Predicted win pct 50-55% danger zone — automatic skip (2024 Finding 9, confirmed 2025)
    #    Both years showed actual win rate <29% in this band, worse than below-50% signals.
    if 50.0 < predicted_win_pct <= 55.0:
        return False, f"Predicted win pct {predicted_win_pct:.1f}% in 50-55% danger zone"

    # ── Filters 8-10: SHORT-SPECIFIC only ────────────────────────────────────

    if direction == -1:

        # 8. Lower circuit guard: if stock near lower circuit, cannot buy back to cover
        if not today_5min.empty:
            open_p        = float(today_5min.iloc[0]["open"])
            lower_circuit = open_p * (1 - 0.10)   # 10% NSE daily circuit band
            current_price = float(today_5min.iloc[-1]["close"])
            if current_price > 0 and current_price <= lower_circuit * (1 + LOWER_CIRCUIT_BUFFER):
                return False, (f"Short blocked: price {current_price:.2f} within "
                               f"{LOWER_CIRCUIT_BUFFER*100:.0f}% of lower circuit {lower_circuit:.2f}")

        # 9. Near 52-week low on a green Nifty day — institutional buy-the-dip risk
        #    Exception: allow if extraordinary consensus (5+ strategies agreeing)
        if week52_low > 0 and nifty_pct_change > NIFTY_GREEN_THRESHOLD:
            current_price = float(today_5min.iloc[-1]["close"]) if not today_5min.empty else 0
            if current_price > 0:
                dist_from_low = (current_price - week52_low) / week52_low
                if dist_from_low < WEEK52_LOW_BUFFER and strategies_agreeing < 5:
                    return False, (f"Short blocked: stock {dist_from_low*100:.1f}% above "
                                   f"52-week low {week52_low:.2f} on green Nifty day")

        # 10. Corporate event blackout proxy: stock moved >5% in prior 3 days
        if recent_3day_move > CORP_EVENT_MOVE_PCT:
            return False, (f"Short blocked: stock moved {recent_3day_move*100:.1f}% in prior "
                           f"3 days — possible corporate event")

    return True, ""

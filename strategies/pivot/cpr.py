"""
Strategy 16: CPR (Central Pivot Range)
  Pivot = (H+L+C)/3,  BC = (H+L)/2,  TC = Pivot + (Pivot - BC)
  Narrow CPR (<0.3%) → trending day → use breakouts
  Wide CPR  (>0.8%) → sideways day → use reversions
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class CPR(BaseStrategy):
    name     = "CPR"
    category = "pivot"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if prev_day is None or today_5min.empty:
            return self._no_signal()

        H, L, C = float(prev_day["high"]), float(prev_day["low"]), float(prev_day["close"])
        pivot = (H + L + C) / 3
        bc    = (H + L) / 2
        tc    = pivot + (pivot - bc)
        cpr_width_pct = abs(tc - bc) / pivot

        # Narrow CPR → trending day → trade breakout above TC or below BC
        if cpr_width_pct < 0.003:
            for _, c in today_5min.iterrows():
                if self._after_cutoff(c["datetime"]):
                    break
                if c["close"] > tc:
                    stop   = bc
                    target = tc + 2 * (tc - bc)
                    return self._buy(tc, target, stop,
                                      signal_time=self._candle_time(c["datetime"]),
                                      reason=f"CPR: narrow CPR, breakout above TC={tc:.2f}")
                if c["close"] < bc:
                    stop   = tc
                    target = bc - 2 * (tc - bc)
                    return self._sell(bc, target, stop,
                                       signal_time=self._candle_time(c["datetime"]),
                                       reason=f"CPR: narrow CPR, breakdown below BC={bc:.2f}")

        # Wide CPR → sideways day → trade reversion at TC or BC
        elif cpr_width_pct > 0.008:
            vwap = self._compute_vwap(today_5min)
            for i, (_, c) in enumerate(today_5min.iterrows()):
                if self._after_cutoff(c["datetime"]):
                    break
                if c["low"] <= bc <= c["high"]:   # touch BC from below
                    return self._buy(bc, pivot, bc * 0.985,
                                      signal_time=self._candle_time(c["datetime"]),
                                      reason=f"CPR: wide CPR, reversion from BC={bc:.2f}")
                if c["low"] <= tc <= c["high"]:   # touch TC from above
                    return self._sell(tc, pivot, tc * 1.015,
                                       signal_time=self._candle_time(c["datetime"]),
                                       reason=f"CPR: wide CPR, reversion from TC={tc:.2f}")
        return self._no_signal()

"""
PIN-BAR — single-candle rejection pattern (Hammer / Shooting Star).

The only single-candle rejection pattern in the system. All 22 existing
strategies use multi-bar logic.

Hammer (lower wick dominant, forms at support/VWAP) → BUY (+1).
Shooting Star (upper wick dominant, forms at resistance/VWAP) → SHORT (-1).

Criteria:
  - Body occupies ≤30% of total bar range
  - Dominant wick ≥2× body length
  - Volume > 1.2× 20-bar average (institutional participation)
  - At intraday support or resistance (within 0.5% of VWAP or recent S/R level)
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class PinBar(BaseStrategy):
    name     = "PIN-BAR"
    category = "dual"

    MAX_BODY_RATIO  = 0.30    # body must be ≤30% of bar range
    MIN_WICK_RATIO  = 2.0     # dominant wick ≥2× body
    VOL_MULT        = 1.2     # volume > 1.2× 20-bar average
    LEVEL_MARGIN    = 0.005   # within 0.5% of VWAP / S/R level

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if today_5min.empty or len(today_5min) < 4:
            return self._no_signal()

        vwap    = self._compute_vwap(today_5min)
        avg_vol = self._avg_vol(today_5min)
        pdh     = float(prev_day["high"]) if prev_day is not None else None
        pdl     = float(prev_day["low"])  if prev_day is not None else None

        for i, (idx, c) in enumerate(today_5min.iterrows()):
            if self._after_cutoff(c["datetime"]):
                break

            o     = float(c["open"])
            h     = float(c["high"])
            l     = float(c["low"])
            cl    = float(c["close"])
            vol   = float(c["volume"])
            bar_range = h - l

            if bar_range < 0.001:
                continue

            body      = abs(cl - o)
            upper_w   = h - max(o, cl)
            lower_w   = min(o, cl) - l

            body_ratio = body / bar_range
            if body_ratio > self.MAX_BODY_RATIO:
                continue
            if body == 0:
                body = bar_range * 0.01   # avoid zero-division

            if vol < avg_vol * self.VOL_MULT:
                continue

            cur_vwap = float(vwap.iloc[i])

            # Hammer: lower wick dominant, price at support/VWAP
            if lower_w >= upper_w and lower_w >= body * self.MIN_WICK_RATIO:
                near_support = (
                    abs(l - cur_vwap) / cur_vwap < self.LEVEL_MARGIN or
                    (pdl and abs(l - pdl) / pdl < self.LEVEL_MARGIN)
                )
                if near_support:
                    entry  = cl
                    stop   = l * 0.998
                    target = cl + 1.5 * (cl - stop)
                    return self._buy(
                        entry, target, stop,
                        signal_time=self._candle_time(c["datetime"]),
                        reason=f"PIN-BAR Hammer: lower wick {lower_w:.2f} at VWAP {cur_vwap:.2f}",
                    )

            # Shooting Star: upper wick dominant, price at resistance/VWAP
            if upper_w >= lower_w and upper_w >= body * self.MIN_WICK_RATIO:
                near_resist = (
                    abs(h - cur_vwap) / cur_vwap < self.LEVEL_MARGIN or
                    (pdh and abs(h - pdh) / pdh < self.LEVEL_MARGIN)
                )
                if near_resist:
                    entry  = cl
                    stop   = h * 1.002
                    target = cl - 1.5 * (stop - cl)
                    return self._sell(
                        entry, target, stop,
                        signal_time=self._candle_time(c["datetime"]),
                        reason=f"PIN-BAR ShootingStar: upper wick {upper_w:.2f} at VWAP {cur_vwap:.2f}",
                    )

        return self._no_signal()

    @staticmethod
    def _avg_vol(today_5min) -> float:
        return float(today_5min["volume"].mean()) or 1.0

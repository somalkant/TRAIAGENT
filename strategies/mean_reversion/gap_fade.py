"""Strategy 9: Gap Fade — fade gaps >3% that historically fill intraday."""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class GapFade(BaseStrategy):
    name     = "GAP-FADE"
    category = "mean_reversion"
    GAP_MIN  = 0.03   # 3% gap minimum to fade

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if prev_day is None or today_5min.empty:
            return self._no_signal()

        prev_close = float(prev_day["close"])
        day_open   = float(today_5min.iloc[0]["open"])
        gap_pct    = (day_open - prev_close) / prev_close

        if abs(gap_pct) < self.GAP_MIN:
            return self._no_signal()

        # Only fade if first candle doesn't strongly continue the gap direction
        first_c = today_5min.iloc[0]
        candle_body_pct = abs(first_c["close"] - first_c["open"]) / (first_c["open"] + 1e-9)

        if gap_pct > self.GAP_MIN:   # gap-up → fade (sell)
            # Don't fade if first candle is a strong bull candle (gap continuation)
            if first_c["close"] > first_c["open"] and candle_body_pct > 0.005:
                return self._no_signal()
            entry  = day_open
            target = prev_close
            stop   = day_open * 1.02
            return self._sell(entry, target, stop,
                               signal_time="09:15",
                               reason=f"GAP-FADE: gap-up {gap_pct*100:.1f}%, fading back to {prev_close:.2f}")

        if gap_pct < -self.GAP_MIN:  # gap-down → fade (buy)
            if first_c["close"] < first_c["open"] and candle_body_pct > 0.005:
                return self._no_signal()
            entry  = day_open
            target = prev_close
            stop   = day_open * 0.98
            return self._buy(entry, target, stop,
                              signal_time="09:15",
                              reason=f"GAP-FADE: gap-down {gap_pct*100:.1f}%, fading back to {prev_close:.2f}")
        return self._no_signal()

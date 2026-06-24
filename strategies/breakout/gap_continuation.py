"""Strategy 4: Gap Continuation — gap up >1%, buy first pullback to VWAP within 30 min."""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class GapContinuation(BaseStrategy):
    name     = "GAP-CONT"
    category = "breakout"
    GAP_MIN  = 0.01   # 1% minimum gap

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if prev_day is None or today_5min.empty:
            return self._no_signal()

        prev_close = float(prev_day["close"])
        day_open   = float(today_5min.iloc[0]["open"])
        gap_pct    = (day_open - prev_close) / prev_close

        if gap_pct < self.GAP_MIN:
            return self._no_signal()

        vwap = self._compute_vwap(today_5min)
        first_30 = today_5min.iloc[:6]  # first 30 min = 6 candles

        for i, (idx, c) in enumerate(first_30.iterrows()):
            if self._after_cutoff(c["datetime"]):
                break
            v = vwap.iloc[i]
            if c["low"] <= v <= c["high"]:   # candle touches VWAP (pullback)
                entry  = v
                stop   = today_5min["low"].iloc[:i+1].min()
                target = entry + 2 * (entry - stop)
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"GAP-CONT: gap {gap_pct*100:.1f}%, pullback to VWAP={v:.2f}")
        return self._no_signal()

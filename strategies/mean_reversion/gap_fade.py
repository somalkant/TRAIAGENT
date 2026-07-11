"""
Strategy 9: Gap Fade — fade gaps >3% that historically fill intraday.

Waits out the post-open warm-up window (first 15 min) before fading: fading
the raw open risks entering mid-sweep, before the gap has actually started
reverting. Entry only fires once price has reverted back through the open by
the warm-up close; stop sits just beyond the sweep extreme reached during the
warm-up window rather than a flat % off the open.
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class GapFade(BaseStrategy):
    name     = "GAP-FADE"
    category = "mean_reversion"
    GAP_MIN     = 0.03   # 3% gap minimum to fade
    WARMUP_BARS = 3       # first 15 min (3 x 5-min bars) before fading

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if prev_day is None or today_5min.empty or len(today_5min) < self.WARMUP_BARS:
            return self._no_signal()

        prev_close = float(prev_day["close"])
        day_open   = float(today_5min.iloc[0]["open"])
        gap_pct    = (day_open - prev_close) / prev_close

        if abs(gap_pct) < self.GAP_MIN:
            return self._no_signal()

        warmup      = today_5min.iloc[:self.WARMUP_BARS]
        warmup_last = warmup.iloc[-1]
        if not self._after_warmup(warmup_last["datetime"]):
            return self._no_signal()
        warmup_close = float(warmup_last["close"])

        if gap_pct > self.GAP_MIN:   # gap-up → fade (sell)
            # Only fade once price has actually reverted back below the open
            if warmup_close >= day_open:
                return self._no_signal()
            sweep_high = float(warmup["high"].max())
            entry  = warmup_close
            target = prev_close
            stop   = sweep_high * 1.005     # behind the sweep high, not a flat % of open
            return self._sell(entry, target, stop,
                               signal_time=self._candle_time(warmup_last["datetime"]),
                               reason=f"GAP-FADE: gap-up {gap_pct*100:.1f}%, reverted below open, fading to {prev_close:.2f}")

        if gap_pct < -self.GAP_MIN:  # gap-down → fade (buy)
            if warmup_close <= day_open:
                return self._no_signal()
            sweep_low = float(warmup["low"].min())
            entry  = warmup_close
            target = prev_close
            stop   = sweep_low * 0.995
            return self._buy(entry, target, stop,
                              signal_time=self._candle_time(warmup_last["datetime"]),
                              reason=f"GAP-FADE: gap-down {gap_pct*100:.1f}%, reverted above open, fading to {prev_close:.2f}")
        return self._no_signal()

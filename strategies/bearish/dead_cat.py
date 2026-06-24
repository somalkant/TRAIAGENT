"""
Dead Cat Bounce — gap-down bounce fade.

Stock has gapped down >3% at open. During the session it bounces 1-2%
toward VWAP on declining volume. The bounce loses steam before reaching
VWAP. Short on the first bar where price starts declining from the
bounce high with volume below the gap-down bar's volume.

Target: morning gap-down low. Stop: VWAP.
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class DeadCatBounce(BaseStrategy):
    name     = "DEAD-CAT"
    category = "bearish"

    MIN_GAP_PCT   = 0.03   # gap-down must be ≥3%
    MIN_BOUNCE_PCT = 0.01  # bounce must be ≥1% from low
    VOL_DECAY     = 0.85   # bounce volume must be below gap-bar volume × 85%

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if history_5min.empty or today_5min.empty or len(today_5min) < 4:
            return self._no_signal()
        if prev_day is None:
            return self._no_signal()

        prev_close = float(prev_day["close"])
        open_p     = float(today_5min.iloc[0]["open"])
        gap_pct    = (prev_close - open_p) / prev_close

        if gap_pct < self.MIN_GAP_PCT:
            return self._no_signal()   # not a gap-down day

        gap_bar_vol = float(today_5min.iloc[0]["volume"])
        gap_low     = float(today_5min.iloc[0]["low"])

        # VWAP up to current bar
        vwap = self._compute_vwap(today_5min)

        bounce_low  = float(today_5min.iloc[1]["low"]) if len(today_5min) > 1 else gap_low
        bounce_high = bounce_low

        for i, (idx, c) in enumerate(today_5min.iterrows()):
            if i < 1:
                continue
            if self._after_cutoff(c["datetime"]):
                break

            close = float(c["close"])
            high  = float(c["high"])
            vol   = float(c["volume"])
            cur_vwap = float(vwap.iloc[i])

            # Track bounce high
            if high > bounce_high:
                bounce_high = high

            bounce_pct = (bounce_high - bounce_low) / bounce_low
            if bounce_pct < self.MIN_BOUNCE_PCT:
                continue

            # Bounce must not have reached VWAP yet
            if bounce_high >= cur_vwap:
                continue

            # Signal: price declining from bounce high, volume falling below gap bar
            if close < bounce_high * 0.998 and vol < gap_bar_vol * self.VOL_DECAY:
                entry  = close
                target = gap_low              # target: morning low
                stop   = cur_vwap            # stop: VWAP
                return self._sell(
                    entry, target, stop,
                    signal_time=self._candle_time(c["datetime"]),
                    reason=f"Dead Cat: gap-down {gap_pct*100:.1f}%, bounce fading below VWAP {cur_vwap:.2f}",
                )

        return self._no_signal()

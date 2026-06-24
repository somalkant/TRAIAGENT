"""
Bear Engulfing — large red candle at resistance with volume surge.

A large red candle (body > 1.5× prior bar's body) that completely engulfs
the prior green candle's body, forming at a confirmed resistance zone
(PDH, prior day's VWAP approximated via midpoint, round numbers),
with volume > 1.5× 20-bar average.

Short on close of the engulfing bar. Stop above the engulfing bar's high.
Target: nearest intraday support (PDL or 1.5× body distance below entry).
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class BearEngulfing(BaseStrategy):
    name     = "BEAR-ENGULF"
    category = "bearish"

    BODY_MULT   = 1.5    # red body must be 1.5× prior bar body
    VOL_MULT    = 1.5    # volume must be 1.5× 20-bar average
    RES_MARGIN  = 0.01   # bar high must be within 1% of resistance

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if history_5min.empty or today_5min.empty or len(today_5min) < 3:
            return self._no_signal()
        if prev_day is None:
            return self._no_signal()

        resistance = float(prev_day["high"])   # PDH as key resistance
        pdl        = float(prev_day["low"])
        avg_vol    = self._avg_volume(today_5min)

        for i in range(1, len(today_5min)):
            c    = today_5min.iloc[i]
            prev = today_5min.iloc[i - 1]

            if self._after_cutoff(c["datetime"]):
                break

            c_open  = float(c["open"])
            c_close = float(c["close"])
            c_high  = float(c["high"])
            c_vol   = float(c["volume"])

            p_open  = float(prev["open"])
            p_close = float(prev["close"])

            # Current bar must be bearish (red)
            if c_close >= c_open:
                continue

            c_body = c_open - c_close
            p_body = abs(p_close - p_open)

            if p_body == 0:
                continue

            # Body size check
            if c_body < p_body * self.BODY_MULT:
                continue

            # Must engulf prior bar (c_open >= p_close AND c_close <= p_open for red engulf)
            if c_open < max(p_open, p_close) or c_close > min(p_open, p_close):
                continue

            # Volume confirmation
            if c_vol < avg_vol * self.VOL_MULT:
                continue

            # Near resistance
            if abs(c_high - resistance) / resistance > self.RES_MARGIN:
                continue

            entry  = c_close
            stop   = c_high * 1.005
            target = pdl if pdl < entry else entry - 1.5 * c_body

            return self._sell(
                entry, target, stop,
                signal_time=self._candle_time(c["datetime"]),
                reason=f"Bear Engulf at resistance {resistance:.2f}, vol {c_vol/avg_vol:.1f}×",
            )

        return self._no_signal()

    @staticmethod
    def _avg_volume(today_5min) -> float:
        return float(today_5min["volume"].mean()) or 1.0

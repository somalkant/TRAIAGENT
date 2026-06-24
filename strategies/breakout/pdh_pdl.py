"""Strategy 3: PDH/PDL — Previous Day High / Low breakout."""
import pandas as pd
from strategies.base import BaseStrategy, Signal
from datetime import date


class PDH_PDL(BaseStrategy):
    name     = "PDH-PDL"
    category = "breakout"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if prev_day is None or today_5min.empty:
            return self._no_signal()

        pdh = float(prev_day["high"])
        pdl = float(prev_day["low"])
        width = pdh - pdl
        if width <= 0:
            return self._no_signal()

        for _, c in today_5min.iterrows():
            if self._after_cutoff(c["datetime"]):
                break
            if c["close"] > pdh and c["volume"] > 0:
                return self._buy(pdh, pdh + width, pdl,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"PDH-PDL: breakout above PDH={pdh:.2f}")
            if c["close"] < pdl and c["volume"] > 0:
                return self._sell(pdl, pdl - width, pdh,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"PDH-PDL: breakdown below PDL={pdl:.2f}")
        return self._no_signal()

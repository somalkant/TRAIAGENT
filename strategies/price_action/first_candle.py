"""Strategy 15: First 5-min Candle — buy above / sell below first candle of the day."""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class FirstCandle(BaseStrategy):
    name     = "FIRST-CANDLE"
    category = "price_action"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if len(today_5min) < 2:
            return self._no_signal()

        first = today_5min.iloc[0]
        high  = float(first["high"])
        low   = float(first["low"])
        width = high - low
        if width <= 0:
            return self._no_signal()

        for _, c in today_5min.iloc[1:].iterrows():
            if self._after_cutoff(c["datetime"]):
                break
            if c["close"] > high:
                return self._buy(high, high + 2 * width, low,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"FIRST-CANDLE: break above first candle high={high:.2f}")
            if c["close"] < low:
                return self._sell(low, low - 2 * width, high,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"FIRST-CANDLE: break below first candle low={low:.2f}")
        return self._no_signal()

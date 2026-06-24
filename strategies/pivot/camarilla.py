"""
Strategy 17: Camarilla Pivots
  H3 = C + (H-L)×1.1/4    L3 = C - (H-L)×1.1/4
  H4 = C + (H-L)×1.1/2    L4 = C - (H-L)×1.1/2
  Reversal: L3 → buy (stop below L4), target H3
  Breakout: above H4 → momentum long
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class Camarilla(BaseStrategy):
    name     = "CAMARILLA"
    category = "pivot"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if prev_day is None or today_5min.empty:
            return self._no_signal()

        H = float(prev_day["high"])
        L = float(prev_day["low"])
        C = float(prev_day["close"])
        rng = H - L

        h3 = C + rng * 1.1 / 4
        h4 = C + rng * 1.1 / 2
        l3 = C - rng * 1.1 / 4
        l4 = C - rng * 1.1 / 2

        for _, c in today_5min.iterrows():
            if self._after_cutoff(c["datetime"]):
                break

            # Reversal at L3: buy with stop below L4, target H3
            if c["low"] <= l3 and c["close"] > l3:
                return self._buy(l3, h3, l4,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"CAMARILLA: reversal at L3={l3:.2f}, target H3={h3:.2f}")

            # Breakout above H4: momentum long
            if c["close"] > h4:
                return self._buy(h4, h4 + (h4 - l4), h3,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"CAMARILLA: breakout above H4={h4:.2f}")

            # Reversal at H3: sell with stop above H4, target L3
            if c["high"] >= h3 and c["close"] < h3:
                return self._sell(h3, l3, h4,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"CAMARILLA: reversal at H3={h3:.2f}, target L3={l3:.2f}")
        return self._no_signal()

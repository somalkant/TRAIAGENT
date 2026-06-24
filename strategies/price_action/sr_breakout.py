"""Strategy 13: Support/Resistance Breakout — key intraday level break with volume."""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, Signal


class SRBreakout(BaseStrategy):
    name     = "SR-BREAK"
    category = "price_action"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if history_5min.empty or today_5min.empty:
            return self._no_signal()

        recent = history_5min.tail(500)
        highs  = recent["high"].values
        lows   = recent["low"].values

        # Find significant S/R levels using price clustering
        resistance = self._find_level(highs, today_5min.iloc[0]["open"], above=True)
        support    = self._find_level(lows,  today_5min.iloc[0]["open"], above=False)
        avg_vol    = today_5min["volume"].mean() or 1

        for _, c in today_5min.iterrows():
            if self._after_cutoff(c["datetime"]):
                break
            vol_ok = c["volume"] > avg_vol * 1.5

            if resistance and c["close"] > resistance and vol_ok:
                entry  = resistance
                stop   = support or entry * 0.97
                target = entry + 2 * (entry - stop)
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"SR-BREAK: breakout above resistance {resistance:.2f}")

            if support and c["close"] < support and vol_ok:
                entry  = support
                stop   = resistance or entry * 1.03
                target = entry - 2 * (stop - entry)
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"SR-BREAK: breakdown below support {support:.2f}")
        return self._no_signal()

    def _find_level(self, prices, current_price, above: bool, tolerance=0.005):
        candidates = [p for p in prices
                      if (p > current_price * 1.001 if above else p < current_price * 0.999)]
        if not candidates:
            return None
        # Find the most-tested level (histogram peak)
        bins = np.histogram(candidates, bins=50)
        peak_idx = np.argmax(bins[0])
        level = (bins[1][peak_idx] + bins[1][peak_idx+1]) / 2
        return round(level, 2)

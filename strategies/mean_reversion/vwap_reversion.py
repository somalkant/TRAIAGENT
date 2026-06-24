"""Strategy 6: VWAP Reversion — price >1.5% from VWAP, trade back to VWAP."""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class VWAPReversion(BaseStrategy):
    name        = "VWAP-REV"
    category    = "mean_reversion"
    DEVIATION   = 0.015   # 1.5% from VWAP

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if len(today_5min) < 6:
            return self._no_signal()

        vwap = self._compute_vwap(today_5min)

        for i, (idx, c) in enumerate(today_5min.iterrows()):
            if i < 3:   # skip first 15 min (too volatile)
                continue
            if self._after_cutoff(c["datetime"]):
                break

            v   = vwap.iloc[i]
            dev = (c["close"] - v) / v

            if dev < -self.DEVIATION:   # price too far below VWAP → buy reversion
                entry  = c["close"]
                target = v
                stop   = entry * (1 - self.DEVIATION * 1.5)
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"VWAP-REV: price {dev*100:.1f}% below VWAP={v:.2f}, reversion buy")

            if dev > self.DEVIATION:    # price too far above VWAP → sell reversion
                entry  = c["close"]
                target = v
                stop   = entry * (1 + self.DEVIATION * 1.5)
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"VWAP-REV: price {dev*100:.1f}% above VWAP={v:.2f}, reversion sell")
        return self._no_signal()

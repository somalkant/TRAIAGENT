"""Strategy 10: EMA Crossover — 9 EMA crosses 21 EMA on 5-min, confirmed by VWAP and volume."""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class EMACrossover(BaseStrategy):
    name     = "EMA-CROSS"
    category = "trend"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        combined = pd.concat([history_5min.tail(100), today_5min]).reset_index(drop=True)
        if len(combined) < 30:
            return self._no_signal()

        ema9  = ta.ema(combined["close"], length=9)
        ema21 = ta.ema(combined["close"], length=21)
        vwap  = self._compute_vwap(combined)

        today_start = len(combined) - len(today_5min)
        avg_vol = today_5min["volume"].mean() if len(today_5min) > 0 else 1

        for i in range(max(today_start + 1, 22), len(combined)):
            c   = combined.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break
            if pd.isna(ema9.iloc[i]) or pd.isna(ema9.iloc[i-1]):
                continue

            cross_up   = ema9.iloc[i-1] <= ema21.iloc[i-1] and ema9.iloc[i] > ema21.iloc[i]
            cross_down = ema9.iloc[i-1] >= ema21.iloc[i-1] and ema9.iloc[i] < ema21.iloc[i]
            above_vwap = c["close"] > vwap.iloc[i]
            vol_ok     = c["volume"] > avg_vol * 1.2

            if cross_up and above_vwap and vol_ok:
                entry  = c["close"]
                stop   = ema21.iloc[i] * 0.995
                target = entry + 2 * (entry - stop)
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"EMA-CROSS: 9EMA crossed above 21EMA, price above VWAP")

            if cross_down and not above_vwap and vol_ok:
                entry  = c["close"]
                stop   = ema21.iloc[i] * 1.005
                target = entry - 2 * (entry - stop) + 2 * (stop - entry)
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"EMA-CROSS: 9EMA crossed below 21EMA, price below VWAP")
        return self._no_signal()

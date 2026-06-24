"""Strategy 12: MACD Crossover — signal line cross with histogram flip on 5-min."""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class MACDCrossover(BaseStrategy):
    name     = "MACD"
    category = "trend"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        combined = pd.concat([history_5min.tail(200), today_5min]).reset_index(drop=True)
        if len(combined) < 40:
            return self._no_signal()

        macd = ta.macd(combined["close"], fast=12, slow=26, signal=9)
        if macd is None:
            return self._no_signal()

        hist_col   = [c for c in macd.columns if "MACDh" in c][0]
        signal_col = [c for c in macd.columns if "MACDs" in c][0]
        macd_col   = [c for c in macd.columns if c.startswith("MACD_")][0]

        today_start = len(combined) - len(today_5min)

        for i in range(max(today_start + 1, 30), len(combined)):
            c = combined.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break
            if pd.isna(macd[hist_col].iloc[i]):
                continue

            hist_flip_bull = macd[hist_col].iloc[i] > 0 and macd[hist_col].iloc[i-1] <= 0
            hist_flip_bear = macd[hist_col].iloc[i] < 0 and macd[hist_col].iloc[i-1] >= 0
            m_val = macd[macd_col].iloc[i]

            if hist_flip_bull:
                entry  = c["close"]
                stop   = entry * 0.985
                target = entry * 1.025
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"MACD: histogram flipped positive, MACD={m_val:.3f}")

            if hist_flip_bear:
                entry  = c["close"]
                stop   = entry * 1.015
                target = entry * 0.975
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"MACD: histogram flipped negative, MACD={m_val:.3f}")
        return self._no_signal()

"""Strategy 20: Stochastic Crossover — %K crosses %D, confirmed by VWAP position."""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class StochasticCrossover(BaseStrategy):
    name     = "STOCHASTIC"
    category = "oscillator"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        combined = pd.concat([history_5min.tail(100), today_5min]).reset_index(drop=True)
        if len(combined) < 20:
            return self._no_signal()

        stoch = ta.stoch(combined["high"], combined["low"], combined["close"],
                         k=14, d=3, smooth_k=3)
        if stoch is None:
            return self._no_signal()

        k_col = [c for c in stoch.columns if "STOCHk" in c][0]
        d_col = [c for c in stoch.columns if "STOCHd" in c][0]
        vwap  = self._compute_vwap(combined)

        today_start = len(combined) - len(today_5min)

        for i in range(max(today_start + 1, 15), len(combined)):
            c = combined.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break
            if pd.isna(stoch[k_col].iloc[i]):
                continue

            k, k_prev = stoch[k_col].iloc[i], stoch[k_col].iloc[i-1]
            d, d_prev = stoch[d_col].iloc[i], stoch[d_col].iloc[i-1]
            above_vwap = c["close"] > vwap.iloc[i]

            # Oversold crossover: %K crosses above %D from below 20
            if k_prev < d_prev and k > d and k < 30 and above_vwap:
                entry = c["close"]
                stop  = entry * 0.985
                return self._buy(entry, entry * 1.025, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"STOCHASTIC: %K={k:.0f} crossed above %D from oversold")

            # Overbought crossover: %K crosses below %D from above 80
            if k_prev > d_prev and k < d and k > 70 and not above_vwap:
                entry = c["close"]
                stop  = entry * 1.015
                return self._sell(entry, entry * 0.975, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"STOCHASTIC: %K={k:.0f} crossed below %D from overbought")
        return self._no_signal()

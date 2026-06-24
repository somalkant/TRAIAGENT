"""Strategy 8: Bollinger Band Reversion — price at outer band + RSI confirms."""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class BollingerReversion(BaseStrategy):
    name     = "BOLLINGER"
    category = "mean_reversion"
    BB_LEN   = 20
    BB_STD   = 2.0

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        combined = pd.concat([history_5min.tail(150), today_5min]).reset_index(drop=True)
        if len(combined) < self.BB_LEN + 5:
            return self._no_signal()

        bb  = ta.bbands(combined["close"], length=self.BB_LEN, std=self.BB_STD)
        rsi = ta.rsi(combined["close"], length=14)
        if bb is None:
            return self._no_signal()

        lower_col  = [c for c in bb.columns if "BBL" in c][0]
        upper_col  = [c for c in bb.columns if "BBU" in c][0]
        middle_col = [c for c in bb.columns if "BBM" in c][0]

        today_start = len(combined) - len(today_5min)

        for i in range(today_start, len(combined)):
            c = combined.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break
            if pd.isna(bb[lower_col].iloc[i]):
                continue

            lower  = bb[lower_col].iloc[i]
            upper  = bb[upper_col].iloc[i]
            mid    = bb[middle_col].iloc[i]
            r      = rsi.iloc[i] if not pd.isna(rsi.iloc[i]) else 50

            if c["close"] <= lower and r < 35:
                entry  = c["close"]
                stop   = entry * 0.985
                target = mid
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"BOLLINGER: price at lower band {lower:.2f}, RSI={r:.0f}")

            if c["close"] >= upper and r > 65:
                entry  = c["close"]
                stop   = entry * 1.015
                target = mid
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"BOLLINGER: price at upper band {upper:.2f}, RSI={r:.0f}")
        return self._no_signal()

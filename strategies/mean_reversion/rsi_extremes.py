"""Strategy 7: RSI Extremes — RSI(14) on 5-min < 25 buy, > 75 sell."""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class RSIExtremes(BaseStrategy):
    name        = "RSI-EXT"
    category    = "mean_reversion"
    RSI_PERIOD  = 14
    OVERSOLD    = 25
    OVERBOUGHT  = 75

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        # Need history for RSI warm-up
        combined = pd.concat([history_5min.tail(100), today_5min]).reset_index(drop=True)
        if len(combined) < self.RSI_PERIOD + 5:
            return self._no_signal()

        rsi = ta.rsi(combined["close"], length=self.RSI_PERIOD)
        today_start = len(combined) - len(today_5min)

        for i in range(today_start, len(combined)):
            if i >= len(rsi) or pd.isna(rsi.iloc[i]):
                continue
            c   = combined.iloc[i]
            r   = rsi.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break

            if r < self.OVERSOLD:
                entry  = c["close"]
                stop   = entry * 0.98
                target = entry * 1.03
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"RSI-EXT: RSI={r:.1f} oversold, buy reversion")

            if r > self.OVERBOUGHT:
                entry  = c["close"]
                stop   = entry * 1.02
                target = entry * 0.97
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"RSI-EXT: RSI={r:.1f} overbought, sell reversion")
        return self._no_signal()

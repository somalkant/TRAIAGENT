"""Strategy 11: Supertrend (10,3) — direction flip on 5-min chart."""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class Supertrend(BaseStrategy):
    name     = "SUPERTREND"
    category = "trend"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        combined = pd.concat([history_5min.tail(100), today_5min]).reset_index(drop=True)
        if len(combined) < 15:
            return self._no_signal()

        st = ta.supertrend(combined["high"], combined["low"], combined["close"],
                           length=10, multiplier=3.0)
        if st is None or st.empty:
            return self._no_signal()

        dir_col = [c for c in st.columns if "SUPERTd" in c]
        val_col = [c for c in st.columns if c.startswith("SUPERT_") and "d" not in c and "l" not in c and "s" not in c]
        if not dir_col or not val_col:
            return self._no_signal()

        today_start = len(combined) - len(today_5min)

        for i in range(max(today_start + 1, 12), len(combined)):
            c = combined.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break
            if pd.isna(st[dir_col[0]].iloc[i]):
                continue

            flip_bull = st[dir_col[0]].iloc[i] == 1 and st[dir_col[0]].iloc[i-1] == -1
            flip_bear = st[dir_col[0]].iloc[i] == -1 and st[dir_col[0]].iloc[i-1] == 1
            st_val    = st[val_col[0]].iloc[i]

            if flip_bull:
                entry  = c["close"]
                stop   = st_val * 0.998
                target = entry + 2 * (entry - stop)
                return self._buy(entry, target, stop,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"SUPERTREND: flipped bullish, ST={st_val:.2f}")

            if flip_bear:
                entry  = c["close"]
                stop   = st_val * 1.002
                target = entry - 2 * (stop - entry)
                return self._sell(entry, target, stop,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"SUPERTREND: flipped bearish, ST={st_val:.2f}")
        return self._no_signal()

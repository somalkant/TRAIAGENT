"""Strategy 19: VWAP Standard Deviation Bands — VWAP ± 1σ and ± 2σ."""
import pandas as pd
import numpy as np
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class VWAPStdDev(BaseStrategy):
    name     = "VWAP-STDDEV"
    category = "volatility"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if len(today_5min) < 6:
            return self._no_signal()

        df   = today_5min.copy().reset_index(drop=True)
        tp   = (df["high"] + df["low"] + df["close"]) / 3
        vol  = df["volume"]
        cum_vol    = vol.cumsum()
        cum_tpvol  = (tp * vol).cumsum()
        cum_tp2vol = (tp**2 * vol).cumsum()

        vwap  = cum_tpvol / (cum_vol + 1e-9)
        vwap2 = cum_tp2vol / (cum_vol + 1e-9)
        std   = np.sqrt(np.maximum(vwap2 - vwap**2, 0))
        lower2 = vwap - 2 * std
        upper2 = vwap + 2 * std

        rsi = ta.rsi(df["close"], length=5)

        for i in range(5, len(df)):
            c = df.iloc[i]
            if self._after_cutoff(c["datetime"]):
                break
            if std.iloc[i] == 0:
                continue
            r = float(rsi.iloc[i]) if rsi is not None and not pd.isna(rsi.iloc[i]) else 50

            if c["close"] <= lower2.iloc[i] and r < 25:
                entry = c["close"]
                return self._buy(entry, vwap.iloc[i], entry * 0.985,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"VWAP-STDDEV: at -2σ={lower2.iloc[i]:.2f}, RSI={r:.0f}")

            if c["close"] >= upper2.iloc[i] and r > 75:
                entry = c["close"]
                return self._sell(entry, vwap.iloc[i], entry * 1.015,
                                   signal_time=self._candle_time(c["datetime"]),
                                   reason=f"VWAP-STDDEV: at +2σ={upper2.iloc[i]:.2f}, RSI={r:.0f}")
        return self._no_signal()

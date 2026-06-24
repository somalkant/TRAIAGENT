"""Strategy 21: Volume Profile / VPOC — price rejects or breaks VPOC/VAH/VAL."""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, Signal


class VolumeProfile(BaseStrategy):
    name     = "VPOC"
    category = "oscillator"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if history_5min.empty or today_5min.empty:
            return self._no_signal()

        # Use previous day's 5-min data for volume profile
        prev_dates = sorted(history_5min["datetime"].dt.date.unique())
        if not prev_dates:
            return self._no_signal()

        prev_date_data = history_5min[history_5min["datetime"].dt.date == prev_dates[-1]]
        if len(prev_date_data) < 10:
            return self._no_signal()

        vpoc, vah, val = self._compute_vpoc(prev_date_data)

        for _, c in today_5min.iterrows():
            if self._after_cutoff(c["datetime"]):
                break

            # Rejection at VPOC → reversion
            if abs(c["close"] - vpoc) / vpoc < 0.002 and c["volume"] > 0:
                # Price above VPOC and rejecting → sell
                if c["close"] > vpoc and c["open"] > c["close"]:
                    floor_stop = c["close"] * (1 + 0.005)
                    eff_stop = max(vah, floor_stop)
                    return self._sell(c["close"], val, eff_stop,
                                       signal_time=self._candle_time(c["datetime"]),
                                       reason=f"VPOC: rejection at VPOC={vpoc:.2f}")
                # Price below VPOC and rejecting → buy
                if c["close"] < vpoc and c["open"] < c["close"]:
                    floor_stop = c["close"] * (1 - 0.005)
                    eff_stop = min(val, floor_stop)
                    return self._buy(c["close"], vah, eff_stop,
                                      signal_time=self._candle_time(c["datetime"]),
                                      reason=f"VPOC: rejection below VPOC={vpoc:.2f}")

            # Breakout above VAH with volume
            if c["close"] > vah and c["volume"] > prev_date_data["volume"].mean() * 1.5:
                return self._buy(vah, vah + (vah - val), vpoc,
                                  signal_time=self._candle_time(c["datetime"]),
                                  reason=f"VPOC: breakout above VAH={vah:.2f}")
        return self._no_signal()

    def _compute_vpoc(self, df: pd.DataFrame):
        price_bins = np.linspace(df["low"].min(), df["high"].max(), 50)
        vol_profile = np.zeros(len(price_bins) - 1)
        for _, row in df.iterrows():
            for i in range(len(price_bins) - 1):
                if price_bins[i] <= row["close"] < price_bins[i+1]:
                    vol_profile[i] += row["volume"]
                    break

        vpoc_idx = np.argmax(vol_profile)
        vpoc = (price_bins[vpoc_idx] + price_bins[vpoc_idx + 1]) / 2

        # Value Area: 70% of total volume
        total_vol = vol_profile.sum()
        target_vol = total_vol * 0.70
        sorted_idx = np.argsort(vol_profile)[::-1]
        cum_vol = 0
        va_indices = []
        for idx in sorted_idx:
            cum_vol += vol_profile[idx]
            va_indices.append(idx)
            if cum_vol >= target_vol:
                break

        vah_idx = max(va_indices)
        val_idx = min(va_indices)
        vah = price_bins[min(vah_idx + 1, len(price_bins) - 1)]
        val = price_bins[val_idx]
        return vpoc, vah, val

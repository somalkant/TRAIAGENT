"""
Strategy 1: ORB-15  — Opening Range Breakout (first 15 minutes)
Strategy 2: ORB-30  — Opening Range Breakout (first 30 minutes)

Signal logic:
  - Range = high/low of first N candles after market open
  - Buy  signal: price breaks ABOVE range high with volume confirmation
  - Sell signal: price breaks BELOW range low (logged only — long-only system)
  - Volume confirmation: current candle volume > 1.5× avg of range candles
  - Stop: opposite side of the range
  - Target: entry + 2× range width (minimum 1:1.5 RR)
"""

import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, Signal
from datetime import date


class ORB15(BaseStrategy):
    name     = "ORB-15"
    category = "breakout"
    CANDLES  = 3   # 9:15, 9:20, 9:25 → range complete after 3 candles

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        return _orb_signal(self, today_5min, self.CANDLES)


class ORB30(BaseStrategy):
    name     = "ORB-30"
    category = "breakout"
    CANDLES  = 6   # 9:15–9:44 → range complete after 6 candles

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        return _orb_signal(self, today_5min, self.CANDLES)


def _orb_signal(strategy: BaseStrategy, today: pd.DataFrame, range_candles: int) -> Signal:
    if len(today) < range_candles + 2:
        return strategy._no_signal()

    opening_range = today.iloc[:range_candles]
    orb_high  = opening_range["high"].max()
    orb_low   = opening_range["low"].min()
    orb_width = orb_high - orb_low

    if orb_width <= 0:
        return strategy._no_signal()

    avg_range_vol = opening_range["volume"].mean()

    # Scan candles after range for breakout
    post_range = today.iloc[range_candles:]
    for _, candle in post_range.iterrows():
        if strategy._after_cutoff(candle["datetime"]):
            break

        vol_ok = candle["volume"] > avg_range_vol * 1.5

        if candle["close"] > orb_high and vol_ok:
            entry  = orb_high
            stop   = orb_low
            target = entry + 2 * orb_width
            return strategy._buy(entry, target, stop,
                                  signal_time=strategy._candle_time(candle["datetime"]),
                                  reason=f"{strategy.name}: breakout above {orb_high:.2f} (range={orb_width:.2f})")

        if candle["close"] < orb_low and vol_ok:
            entry  = orb_low
            stop   = orb_high
            target = entry - 2 * orb_width
            return strategy._sell(entry, target, stop,
                                   signal_time=strategy._candle_time(candle["datetime"]),
                                   reason=f"{strategy.name}: breakdown below {orb_low:.2f}")

    return strategy._no_signal()

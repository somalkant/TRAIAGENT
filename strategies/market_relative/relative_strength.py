"""Strategy 22: Relative Strength — stock outperforming Nifty 50 in first 30 min."""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class RelativeStrength(BaseStrategy):
    name     = "REL-STR"
    category = "market_relative"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if len(today_5min) < 6 or nifty_today is None or len(nifty_today) < 6:
            return self._no_signal()

        first_30_stock = today_5min.iloc[:6]
        first_30_nifty = nifty_today.iloc[:6]

        stock_open = float(today_5min.iloc[0]["open"])
        nifty_open = float(nifty_today.iloc[0]["open"])
        if stock_open == 0 or nifty_open == 0:
            return self._no_signal()

        stock_ret = (float(first_30_stock.iloc[-1]["close"]) - stock_open) / stock_open
        nifty_ret = (float(first_30_nifty.iloc[-1]["close"]) - nifty_open) / nifty_open

        rel_strength = stock_ret - nifty_ret

        # Stock strongly outperforming Nifty → momentum long
        if rel_strength > 0.005:   # 0.5% outperformance
            entry  = float(today_5min.iloc[5]["close"])
            stop   = entry * 0.985
            target = entry + 2 * (entry - stop)
            return self._buy(entry, target, stop,
                              signal_time=self._candle_time(today_5min.iloc[5]["datetime"]),
                              reason=f"REL-STR: stock +{stock_ret*100:.1f}% vs Nifty +{nifty_ret*100:.1f}% in first 30min")

        # Stock strongly underperforming → bearish (logged only)
        if rel_strength < -0.005:
            entry  = float(today_5min.iloc[5]["close"])
            stop   = entry * 1.015
            target = entry * 0.975
            return self._sell(entry, target, stop,
                               signal_time=self._candle_time(today_5min.iloc[5]["datetime"]),
                               reason=f"REL-STR: stock {stock_ret*100:.1f}% vs Nifty {nifty_ret*100:.1f}% in first 30min")
        return self._no_signal()

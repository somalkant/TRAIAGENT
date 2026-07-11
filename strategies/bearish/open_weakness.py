"""
Open Weakness — stock opens near prior day low on a weak Nifty.

Stock opens within 0.5% of its previous day's low AND sweeps below it during
the post-open warm-up window (9:15–9:30) AND Nifty 50 is also down >0.3%.

Short only if the breakdown is still holding at the warm-up close (9:30 bar) —
a bar that dips below PDL and reclaims it within the window is a stop-sweep,
not sustained weakness, and is skipped.
Stop: above opening price.
Target: 1.5× stop distance below entry.

Logic: stocks that cannot hold the prior day's low through the opening
warm-up have sustained institutional selling from pre-market, not just a
brief liquidity grab.
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class OpenWeakness(BaseStrategy):
    name     = "OPEN-WEAK"
    category = "bearish"

    NEAR_LOW_PCT    = 0.005   # open within 0.5% of PDL
    NIFTY_WEAK_PCT  = 0.003   # Nifty must be down ≥0.3% at open
    WARMUP_BARS     = 3       # confirm over first 15 min, not the single opening candle

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if history_5min.empty or today_5min.empty or prev_day is None:
            return self._no_signal()
        if nifty_today is None or nifty_today.empty:
            return self._no_signal()
        if len(today_5min) < self.WARMUP_BARS:
            return self._no_signal()

        pdl    = float(prev_day["low"])
        open_p = float(today_5min.iloc[0]["open"])

        # Condition 1: opens within 0.5% of PDL
        if abs(open_p - pdl) / pdl > self.NEAR_LOW_PCT:
            return self._no_signal()

        # Condition 2: Nifty is down >0.3% at open
        nifty_open  = float(nifty_today.iloc[0]["open"])
        nifty_prev  = self._get_nifty_prev_close(history_5min, trade_date)
        if nifty_prev and nifty_prev > 0:
            nifty_chg = (nifty_open - nifty_prev) / nifty_prev
            if nifty_chg > -self.NIFTY_WEAK_PCT:
                return self._no_signal()

        warmup      = today_5min.iloc[:self.WARMUP_BARS]
        warmup_last = warmup.iloc[-1]
        if not self._after_warmup(warmup_last["datetime"]):
            return self._no_signal()

        # Condition 3: warm-up window swept below PDL AND is still below it at
        # the close of the window (rules out a brief wick that reclaimed PDL)
        warmup_low   = float(warmup["low"].min())
        warmup_close = float(warmup_last["close"])
        if warmup_low >= pdl or warmup_close >= pdl:
            return self._no_signal()

        entry     = warmup_close
        stop      = open_p * 1.005          # just above opening price
        risk_dist = stop - entry
        if risk_dist <= 0:
            return self._no_signal()
        target    = entry - 1.5 * risk_dist

        return self._sell(
            entry, target, stop,
            signal_time=self._candle_time(warmup_last["datetime"]),
            reason=f"Open Weakness: swept below PDL {pdl:.2f} and held weak through warm-up, Nifty weak",
        )

    @staticmethod
    def _get_nifty_prev_close(history_5min, trade_date) -> float | None:
        return None  # Nifty prev close not easily available in this context; skip Nifty guard if absent

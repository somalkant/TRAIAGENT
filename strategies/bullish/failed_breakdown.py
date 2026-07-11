"""
Failed Breakdown (Bear Trap) — long-side mirror of FAILED-BO.

Price breaks below a key support (PDL, ORB low) on volume, triggering
sell/short signals — but then closes back above support within 1-2 bars on
above-average volume. Trapped shorts become forced buyers.

Logic: identify a support level from history; wait for price to spike
below it then close above it with volume confirmation.
"""
import pandas as pd
from strategies.base import BaseStrategy, Signal


class FailedBreakdown(BaseStrategy):
    name     = "FAILED-BD"
    category = "bullish"

    VOL_MULT      = 1.3    # reversal bar needs 1.3x average volume
    MAX_BARS_DOWN = 2      # how many bars below support before reversal counts as "failed"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if history_5min.empty or today_5min.empty or len(today_5min) < 4:
            return self._no_signal()

        support = self._find_support(history_5min, today_5min)
        if support is None:
            return self._no_signal()

        resistance = self._find_resistance(history_5min, today_5min)
        avg_vol = float(today_5min["volume"].mean()) or 1.0

        bars_below = 0

        for idx, c in today_5min.iterrows():
            if self._after_cutoff(c["datetime"]):
                break

            close = float(c["close"])
            low   = float(c["low"])
            vol   = float(c["volume"])

            if low < support:
                bars_below += 1

            # Reversal: was below support, now closed back above with volume
            if bars_below >= 1 and bars_below <= self.MAX_BARS_DOWN and close > support and vol > avg_vol * self.VOL_MULT:
                entry  = close
                stop   = low * 0.995      # just below the failed breakdown low
                target = resistance if resistance and resistance > entry else entry * 1.03

                return self._buy(
                    entry, target, stop,
                    signal_time=self._candle_time(c["datetime"]),
                    reason=f"Failed BD: bear trap below {support:.2f}, reversed on vol {vol/avg_vol:.1f}x",
                )

            if close < support:
                bars_below = max(bars_below, 1)
            elif close > support * 1.01:
                bars_below = 0   # reset if price rallied far above support

        return self._no_signal()

    def _find_support(self, history_5min, today_5min) -> float | None:
        # PDL (previous day low) is the most reliable intraday support
        if history_5min.empty:
            return None
        daily = (history_5min.groupby(history_5min["datetime"].dt.date)
                 .agg(low=("low", "min")))
        if daily.empty:
            return None
        pdl = float(daily["low"].iloc[-1])
        # Also check ORB low (first 30-min range)
        orb_bars = today_5min[today_5min["datetime"].dt.time <= pd.Timestamp("09:45").time()]
        open_p = float(today_5min.iloc[0]["open"])
        candidates = [pdl]
        if not orb_bars.empty:
            candidates.append(float(orb_bars["low"].min()))
        candidates = [s for s in candidates if s < open_p * 1.005]
        # Use whichever support level today's price is closest to from above
        return float(min(candidates, key=lambda s: open_p - s)) if candidates else None

    def _find_resistance(self, history_5min, today_5min) -> float | None:
        if history_5min.empty:
            return None
        daily = (history_5min.groupby(history_5min["datetime"].dt.date)
                 .agg(high=("high", "max")))
        if daily.empty:
            return None
        return float(daily["high"].iloc[-1])   # PDH as nearest resistance

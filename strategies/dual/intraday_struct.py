"""
Intraday Structure (HHHL / LHLL) — price-structure trend following.

The only price-structure strategy in the system. All 22 existing strategies
are indicator-based.

After 9:30 AM, evaluates the sequence of 5-min pivots:
  HHHL (Higher High, Higher Low) → intraday uptrend → BUY pullbacks (+1)
  LHLL (Lower High, Lower Low)   → intraday downtrend → SHORT bounces (-1)

Requires ≥3 confirmed pivot points after open (fires no earlier than 10:15 AM).
Stop: below last HL (long) or above last LH (short).
Target: prior HH + range (long) or prior LL - range (short).
"""
import pandas as pd
from datetime import time as dtime
from strategies.base import BaseStrategy, Signal


class IntradayStructure(BaseStrategy):
    name     = "INTRADAY-STRUCT"
    category = "dual"

    MIN_BARS_BEFORE_SIGNAL = 12   # ≥1 hour of data (12 × 5-min = 60 min after 9:15)
    MIN_PIVOTS             = 3    # need 3 pivot highs/lows to confirm structure

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        if today_5min.empty or len(today_5min) < self.MIN_BARS_BEFORE_SIGNAL:
            return self._no_signal()

        pivots = self._find_pivots(today_5min)
        if len(pivots) < self.MIN_PIVOTS:
            return self._no_signal()

        return self._evaluate_structure(today_5min, pivots)

    def _find_pivots(self, df: pd.DataFrame) -> list[dict]:
        pivots = []
        n = len(df)
        for i in range(1, n - 1):
            h = float(df.iloc[i]["high"])
            l = float(df.iloc[i]["low"])
            ph = float(df.iloc[i-1]["high"])
            pl = float(df.iloc[i-1]["low"])
            nh = float(df.iloc[i+1]["high"])
            nl = float(df.iloc[i+1]["low"])

            if h > ph and h > nh:
                pivots.append({"type": "H", "price": h, "idx": i,
                                "time": self._candle_time(df.iloc[i]["datetime"])})
            elif l < pl and l < nl:
                pivots.append({"type": "L", "price": l, "idx": i,
                                "time": self._candle_time(df.iloc[i]["datetime"])})

        # Deduplicate consecutive same-type pivots (keep highest H or lowest L)
        merged = []
        for p in pivots:
            if merged and merged[-1]["type"] == p["type"]:
                if p["type"] == "H" and p["price"] > merged[-1]["price"]:
                    merged[-1] = p
                elif p["type"] == "L" and p["price"] < merged[-1]["price"]:
                    merged[-1] = p
            else:
                merged.append(p)

        return merged

    def _evaluate_structure(self, df: pd.DataFrame, pivots: list) -> Signal:
        # Need at least alternating H-L-H or L-H-L to determine structure
        last = pivots[-4:] if len(pivots) >= 4 else pivots
        if len(last) < 3:
            return self._no_signal()

        highs = [p for p in last if p["type"] == "H"]
        lows  = [p for p in last if p["type"] == "L"]

        if len(highs) < 2 or len(lows) < 2:
            return self._no_signal()

        last_h1, last_h2 = highs[-2], highs[-1]
        last_l1, last_l2 = lows[-2],  lows[-1]

        cur_close = float(df.iloc[-1]["close"])
        signal_t  = self._candle_time(df.iloc[-1]["datetime"])

        # HHHL: both highs rising, both lows rising → uptrend
        if (last_h2["price"] > last_h1["price"] and
                last_l2["price"] > last_l1["price"]):
            # BUY on the pullback to last HL
            hl     = last_l2["price"]
            hh     = last_h2["price"]
            rng    = hh - last_l1["price"]
            target = hh + rng
            stop   = hl * 0.997
            if cur_close > hl * 1.001 and cur_close < hh:
                return self._buy(
                    cur_close, target, stop, signal_time=signal_t,
                    reason=f"HHHL uptrend: HH={hh:.2f} HL={hl:.2f}",
                )

        # LHLL: both highs falling, both lows falling → downtrend
        if (last_h2["price"] < last_h1["price"] and
                last_l2["price"] < last_l1["price"]):
            # SHORT on bounce to last LH
            lh     = last_h2["price"]
            ll     = last_l2["price"]
            rng    = last_h1["price"] - last_l1["price"]
            target = ll - rng
            stop   = lh * 1.003
            if cur_close < lh * 0.999 and cur_close > ll:
                return self._sell(
                    cur_close, target, stop, signal_time=signal_t,
                    reason=f"LHLL downtrend: LH={lh:.2f} LL={ll:.2f}",
                )

        return self._no_signal()

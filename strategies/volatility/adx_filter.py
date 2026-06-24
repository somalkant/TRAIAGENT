"""
Strategy 18: ADX Filter (overlay, not standalone)
Returns a regime signal used as a weight modifier by the engine.
direction: +1 = trending (favour breakouts), -1 = sideways (favour reversions), 0 = neutral
"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy, Signal


class ADXFilter(BaseStrategy):
    name     = "ADX-FILTER"
    category = "volatility"

    def generate_signal(self, today_5min, history_5min, prev_day, nifty_today, trade_date) -> Signal:
        combined = pd.concat([history_5min.tail(100), today_5min]).reset_index(drop=True)
        if len(combined) < 20:
            return self._no_signal()

        adx_df = ta.adx(combined["high"], combined["low"], combined["close"], length=14)
        if adx_df is None:
            return self._no_signal()

        adx_col  = [c for c in adx_df.columns if c.startswith("ADX_")][0]
        dmp_col  = [c for c in adx_df.columns if "DMP" in c][0]
        dmn_col  = [c for c in adx_df.columns if "DMN" in c][0]

        last_row = adx_df.iloc[-1]
        adx_val  = last_row[adx_col]
        dmp      = last_row[dmp_col]
        dmn      = last_row[dmn_col]

        if pd.isna(adx_val):
            return self._no_signal()

        # ADX > 25 + DI+ > DI- → strong trend → direction +1
        if adx_val > 25 and dmp > dmn:
            return Signal(strategy=self.name, direction=+1,
                          reason=f"ADX-FILTER: ADX={adx_val:.1f} trending, DI+={dmp:.1f}>DI-={dmn:.1f}")
        # ADX < 20 → sideways → direction -1
        if adx_val < 20:
            return Signal(strategy=self.name, direction=-1,
                          reason=f"ADX-FILTER: ADX={adx_val:.1f} sideways")
        return self._no_signal()

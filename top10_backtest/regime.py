"""
Regime gate (#3) — restrict which strategy CLASS may trade based on the
Nifty day-type, read from the index's own intraday behaviour.

Rationale (from the 10-session live review + a professional-trader consult):
the 10 strategies were selected for uncorrelated *code structure* but in live
trading their *returns* were highly correlated — on losing days 67-78% of all
trades lost together, because momentum and mean-reversion strategies were run
simultaneously every day regardless of whether the day actually trended or
chopped. A trend day shreds mean-reversion; a chop day shreds breakouts. The
single highest-leverage fix is to let the *index* arbitrate: enable momentum
strategies (direction-aligned) only on trend days, reversion strategies only on
chop days. The two "trapped-trader" setups (FAILED-BO/FAILED-BD) are treated as
regime-agnostic — their premise (forced unwinding of trapped positions) isn't
cleanly a trend or a chop phenomenon.

Classification is deliberately simple and computable from OHLCV alone: the
Nifty opening range (first few bars) + which side of VWAP price holds + a
true-range expansion check to avoid labelling a limp drift a "trend". It is
UNKNOWN (all strategies allowed) before TOP10_REGIME_DECISION_TIME, since many
strategies legitimately fire in the 09:20-09:40 window before any index
day-type can be read.

Pure function of (nifty_today, at_time) with a strict no-lookahead truncation —
safe to call identically from the day-by-day backtest (which passes the whole
day's Nifty bars) and the live loop (which only has bars up to now).
"""
from __future__ import annotations

from datetime import time as dtime

import pandas as pd

from config.settings import (
    TOP10_REGIME_DECISION_TIME,
    TOP10_REGIME_OR_BARS,
    TOP10_REGIME_ATR_BARS,
    TOP10_REGIME_ATR_EXPANSION,
    TOP10_STRATEGY_CLASS,
)

UNKNOWN    = "UNKNOWN"
TREND_UP   = "TREND_UP"
TREND_DOWN = "TREND_DOWN"
CHOP       = "CHOP"


def classify_regime(nifty_today: pd.DataFrame, at_time: str | dtime) -> str:
    """
    Returns "TREND_UP" / "TREND_DOWN" / "CHOP" / "UNKNOWN".

    nifty_today : today's Nifty-50 5-min OHLCV bars (may contain bars after
                  `at_time` — this function truncates itself, no-lookahead).
    at_time     : the decision moment, as "HH:MM" or a datetime.time. The
                  regime is read from Nifty bars labelled at or before this.
    """
    t = _as_time(at_time)
    if t is None or t < TOP10_REGIME_DECISION_TIME:
        return UNKNOWN
    if nifty_today is None or nifty_today.empty:
        return UNKNOWN

    bars = _truncate(nifty_today, t)
    if len(bars) <= TOP10_REGIME_OR_BARS:
        return UNKNOWN

    opening = bars.iloc[:TOP10_REGIME_OR_BARS]
    or_high = float(opening["high"].max())
    or_low  = float(opening["low"].min())

    vwap = _vwap(bars)
    last_close = float(bars.iloc[-1]["close"])

    above = last_close > or_high and last_close > vwap
    below = last_close < or_low and last_close < vwap
    if not above and not below:
        return CHOP

    # A genuine trend should also be expanding range, not a limp drift. If we
    # don't yet have enough bars for the baseline, accept the OR+VWAP read.
    if not _range_expanding(bars):
        return CHOP

    return TREND_UP if above else TREND_DOWN


def strategy_allowed(strategy_name: str, side: str, regime: str) -> bool:
    """
    Whether a strategy/side may take a new entry under the current regime.

    - UNKNOWN  : everything allowed (pre-decision-time).
    - AGNOSTIC : the trapped-trader setups, always allowed.
    - CHOP     : reversion strategies only.
    - TREND_UP : momentum LONG only (don't fight or fade the trend).
    - TREND_DOWN: momentum SHORT only.
    """
    if regime == UNKNOWN:
        return True

    cls = TOP10_STRATEGY_CLASS.get(strategy_name, "AGNOSTIC")
    if cls == "AGNOSTIC":
        return True

    if regime == CHOP:
        return cls == "REVERSION"

    if regime == TREND_UP:
        return cls == "MOMENTUM" and side == "LONG"
    if regime == TREND_DOWN:
        return cls == "MOMENTUM" and side == "SHORT"

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _as_time(at_time: str | dtime) -> dtime | None:
    if isinstance(at_time, dtime):
        return at_time
    if not at_time:
        return None
    try:
        h, m = map(int, str(at_time).split(":"))
        return dtime(h, m)
    except Exception:
        return None


def _truncate(nifty_today: pd.DataFrame, t: dtime) -> pd.DataFrame:
    df = nifty_today.sort_values("datetime")
    return df[df["datetime"].dt.time <= t]


def _vwap(bars: pd.DataFrame) -> float:
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    vol = bars["volume"]
    denom = float(vol.sum())
    if denom <= 0:
        return float(bars.iloc[-1]["close"])
    return float((tp * vol).sum() / denom)


def _true_range_series(bars: pd.DataFrame) -> pd.Series:
    prev_close = bars["close"].shift(1)
    hl = bars["high"] - bars["low"]
    hc = (bars["high"] - prev_close).abs()
    lc = (bars["low"] - prev_close).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def _range_expanding(bars: pd.DataFrame) -> bool:
    """Recent range vs the trailing baseline. If there isn't enough history for
    a baseline yet, don't block the trend read (return True)."""
    tr = _true_range_series(bars)
    if len(tr) < TOP10_REGIME_ATR_BARS + 3:
        return True
    recent   = float(tr.iloc[-3:].mean())
    baseline = float(tr.iloc[-(TOP10_REGIME_ATR_BARS + 3):-3].mean())
    if baseline <= 0:
        return True
    return recent >= TOP10_REGIME_ATR_EXPANSION * baseline

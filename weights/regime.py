"""Regime-based weight modifiers applied before composite scoring.

Phase 2B adds get_direction_bias() — a separate direction-level tilt
applied when comparing the best long candidate vs the best short candidate.
"""
from config.settings import (HIGH_VIX_THRESHOLD, HIGH_ADX_THRESHOLD,
                              BREAKOUT_REGIME_MULT, REVERSION_REGIME_MULT,
                              BREAKOUT_STRATEGIES, REVERSION_STRATEGIES,
                              SHORT_REGIME_VIX_MULT, LONG_REGIME_BULLISH_MULT,
                              SHORT_REGIME_BEARISH_MULT,
                              NIFTY_BULLISH_THRESHOLD, NIFTY_BEARISH_THRESHOLD)


def get_regime_modifiers(weights: dict, vix: float = 15.0, adx: float = 20.0) -> dict:
    """
    Returns per-strategy multipliers based on current market regime.
    Applied daily — multiplied on top of adaptive weights in composite scorer.
    """
    modifiers = {name: 1.0 for name in weights}

    if vix > HIGH_VIX_THRESHOLD:
        for name in BREAKOUT_STRATEGIES:
            if name in modifiers:
                modifiers[name] = BREAKOUT_REGIME_MULT

    elif adx > HIGH_ADX_THRESHOLD and vix < HIGH_VIX_THRESHOLD:
        for name in REVERSION_STRATEGIES:
            if name in modifiers:
                modifiers[name] = REVERSION_REGIME_MULT

    return modifiers


def get_direction_bias(vix: float = 15.0, nifty_pct_change: float = 0.0) -> tuple[float, float]:
    """
    Returns (long_mult, short_mult) direction-level bias applied when
    comparing the best long candidate vs the best short candidate.

    Rules (applied in order — non-exclusive):
      VIX > 20          → short_mult × SHORT_REGIME_VIX_MULT (volatile market favours shorts)
      Nifty > +1.5%     → long_mult  × LONG_REGIME_BULLISH_MULT  (tilt longs on green day)
      Nifty < -1.5%     → short_mult × SHORT_REGIME_BEARISH_MULT (tilt shorts on red day)
      Otherwise         → no bias (1.0, 1.0)

    Biases can stack: e.g. VIX > 20 AND Nifty < -1.5% → short_mult = 1.3 × 1.2 = 1.56.
    A truly exceptional long signal (score >> threshold) can still win on a red day.
    """
    long_mult  = 1.0
    short_mult = 1.0

    if vix > HIGH_VIX_THRESHOLD:
        short_mult *= SHORT_REGIME_VIX_MULT

    if nifty_pct_change > NIFTY_BULLISH_THRESHOLD:
        long_mult  *= LONG_REGIME_BULLISH_MULT

    if nifty_pct_change < NIFTY_BEARISH_THRESHOLD:
        short_mult *= SHORT_REGIME_BEARISH_MULT

    return long_mult, short_mult

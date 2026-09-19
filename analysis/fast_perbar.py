"""
Exact, faster per-bar evaluation of two strategies that must be recomputed at every scan.

Both only depend on bars up to the scan, so they can be computed once per stock-day and read
at bar k — identical to calling generate_signal(today.iloc[:k], ...) k times (verified in
tests/verify_fast_perbar via analysis.fast_perbar.verify):

  ADX-FILTER       ADX / DI+ / DI- use Wilder smoothing (causal), so the last row of the ADX computed
                   on history.tail(100)+today[:k] equals row k of the ADX computed on the full day.
  INTRADAY-STRUCT  a pivot at bar i needs bar i+1 to confirm it; the de-duplication is a left fold,
                   so the pivots for today[:k] are the full-day raw pivots with idx <= k-2, folded.
                   The strategy's own _evaluate_structure is reused unchanged.
"""
from __future__ import annotations

import pandas as pd
import pandas_ta as ta

from strategies import ALL_STRATEGIES
from strategies.base import Signal

_S = {s.name: s for s in ALL_STRATEGIES}
_ADX, _IS = _S["ADX-FILTER"], _S["INTRADAY-STRUCT"]


def adx_signals(today: pd.DataFrame, hist: pd.DataFrame) -> list[Signal]:
    """sigs[k-1] == ADX-FILTER.generate_signal(today.iloc[:k], hist, ...) for k = 1..len(today)."""
    h = hist.tail(100)
    combined = pd.concat([h, today]).reset_index(drop=True)
    out = []
    adx_df = ta.adx(combined["high"], combined["low"], combined["close"], length=14) if len(combined) >= 20 else None
    if adx_df is not None:
        a = adx_df[[c for c in adx_df.columns if c.startswith("ADX_")][0]].values
        p = adx_df[[c for c in adx_df.columns if "DMP" in c][0]].values
        n = adx_df[[c for c in adx_df.columns if "DMN" in c][0]].values
    for k in range(1, len(today) + 1):
        r = len(h) + k - 1                          # last row of the truncated combined frame
        if adx_df is None or len(h) + k < 20 or pd.isna(a[r]):
            out.append(Signal(strategy=_ADX.name, direction=0)); continue
        if a[r] > 25 and p[r] > n[r]:
            out.append(Signal(strategy=_ADX.name, direction=+1,
                              reason=f"ADX-FILTER: ADX={a[r]:.1f} trending, DI+={p[r]:.1f}>DI-={n[r]:.1f}"))
        elif a[r] < 20:
            out.append(Signal(strategy=_ADX.name, direction=-1, reason=f"ADX-FILTER: ADX={a[r]:.1f} sideways"))
        else:
            out.append(Signal(strategy=_ADX.name, direction=0))
    return out


def intraday_struct_signals(today: pd.DataFrame) -> list[Signal]:
    """sigs[k-1] == INTRADAY-STRUCT.generate_signal(today.iloc[:k], ...) for k = 1..len(today)."""
    H, L = today["high"].values.astype(float), today["low"].values.astype(float)
    labels = today["datetime"].dt.strftime("%H:%M").values
    raw = []
    for i in range(1, len(today) - 1):
        if H[i] > H[i - 1] and H[i] > H[i + 1]:
            raw.append({"type": "H", "price": H[i], "idx": i, "time": labels[i]})
        elif L[i] < L[i - 1] and L[i] < L[i + 1]:
            raw.append({"type": "L", "price": L[i], "idx": i, "time": labels[i]})
    out, merged, j = [], [], 0
    for k in range(1, len(today) + 1):
        while j < len(raw) and raw[j]["idx"] <= k - 2:          # fold in pivots confirmed by bar k-1
            p = raw[j]; j += 1
            if merged and merged[-1]["type"] == p["type"]:
                if (p["type"] == "H" and p["price"] > merged[-1]["price"]) or \
                   (p["type"] == "L" and p["price"] < merged[-1]["price"]):
                    merged[-1] = p
            else:
                merged.append(p)
        if k < _IS.MIN_BARS_BEFORE_SIGNAL or len(merged) < _IS.MIN_PIVOTS:
            out.append(Signal(strategy=_IS.name, direction=0)); continue
        out.append(_IS._evaluate_structure(today.iloc[:k], list(merged)))
    return out


def verify(n_stockdays: int = 40, seed: int = 0) -> dict:
    """Compare against the real strategy calls at every bar; returns mismatch counts."""
    import random
    from datetime import date
    from analysis import replay as R
    from backtester.engine import _get_prev_day_ohlc
    random.seed(seed)
    days = [date(2025, 3, 12), date(2025, 9, 4), date(2026, 2, 17), date(2026, 8, 20)]
    syms = random.sample(R.universe(), max(1, n_stockdays // len(days)))
    blk = R.Block(days, syms)
    key = lambda s: (s.direction, round(s.entry, 6), round(s.target, 6), round(s.stop, 6), s.signal_time)
    mism = {"ADX-FILTER": 0, "INTRADAY-STRUCT": 0}; checked = 0
    for d in days:
        nt = blk.nifty[blk.nifty.datetime.dt.date == d]
        for s in syms:
            today, hist = blk.split(s, d)
            if today.empty or hist.empty:
                continue
            prev = _get_prev_day_ohlc(hist, d)
            fa, fi = adx_signals(today, hist), intraday_struct_signals(today)
            for k in range(1, len(today) + 1):
                tt = today.iloc[:k]
                mism["ADX-FILTER"] += key(_ADX.generate_signal(tt, hist, prev, nt, d)) != key(fa[k - 1])
                mism["INTRADAY-STRUCT"] += key(_IS.generate_signal(tt, hist, prev, nt, d)) != key(fi[k - 1])
                checked += 1
    return {"bar_checks": checked, "mismatches": mism}

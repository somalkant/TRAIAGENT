"""
Scenario grid for the LONG book: selection x filters x entry x exit, evaluated separately on
2025 (in-sample for choosing) and 2026 (out-of-sample check), all at the same fixed notional.

Only information available at the decision is used for every filter (p_dec = scan bar's open; the
bar-mid `px` is used only as the entry price — selecting on it would peek at the bar's close):
  runup_pct    stock price at the decision vs its own 09:15 open
  nifty_now_pct NIFTY's last closed bar vs NIFTY's 09:15 open (nifty_pct = NIFTY opening gap vs prev close)
  vwap_pct     stock price at the decision vs its intraday VWAP over closed bars
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from analysis.policies import trades_from_rows, summarize, ExitRule, LIVE_EXIT, tradeable
from analysis.replay import load_nifty
from analysis.simulate import day_bars

TRADEABLE = tradeable       # passed expiry / geometry / quality, price still between stop and target


def add_features(cand: pd.DataFrame, cache: str | None = None) -> pd.DataFrame:
    """Adds runup_pct / nifty_now_pct / vwap_pct to the tradeable (quality-passing) rows only.
    Computed once per stock-day (cumulative VWAP, first open) and per day (NIFTY path), then indexed
    by scan. If `cache` is given, results are stored/reused there (keyed on the input rows)."""
    from pathlib import Path
    c = cand[TRADEABLE(cand)].copy()
    sig = str(pd.util.hash_pandas_object(c[["date", "scan", "symbol"]], index=False).sum())
    if cache and Path(cache).exists():
        f = pd.read_parquet(cache)
        if f.attrs.get("sig") == sig or (len(f) == len(c) and "sig" in f.columns and f["sig"].iloc[0] == sig):
            return f.drop(columns="sig", errors="ignore")
    n = load_nifty(c.date.min().date(), c.date.max().date())
    n["d"] = n.datetime.dt.date
    n["m"] = n.datetime.dt.hour * 60 + n.datetime.dt.minute
    nif = {d: (g.m.values, g.close.values, float(g.open.iloc[0])) for d, g in n.groupby("d")}
    c["B"] = c.scan.str[:2].astype(int) * 60 + c.scan.str[3:].astype(int)
    ru = np.full(len(c), np.nan); nw = np.full(len(c), np.nan); vw = np.full(len(c), np.nan)
    pos = {k: i for i, k in enumerate(c.index)}
    for (d, sym), g in c.groupby(["date", "symbol"]):
        b = day_bars(sym, d.date())
        if b.empty:
            continue
        m = b.m.values; o = float(b.open.iloc[0])
        tp = ((b.high + b.low + b.close) / 3).values; vol = b.volume.values.astype(float)
        cum_pv, cum_v = np.cumsum(tp * vol), np.cumsum(vol)
        nm, nc, no = nif.get(d.date(), (None, None, None))
        for idx, B, px in zip(g.index, g.B.values, g.p_dec.values):
            i = pos[idx]
            k = np.searchsorted(m, B - 5, side="right") - 1          # last closed bar
            ru[i] = (px - o) / o * 100
            if k >= 0 and cum_v[k] > 0:
                vw[i] = (px / (cum_pv[k] / cum_v[k]) - 1) * 100
            if nm is not None:
                j = np.searchsorted(nm, B - 5, side="right") - 1
                if j >= 0:
                    nw[i] = (nc[j] / no - 1) * 100
    c["runup_pct"], c["nifty_now_pct"], c["vwap_pct"] = ru, nw, vw
    c = c.drop(columns="B")
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        c.assign(sig=sig).to_parquet(cache)
    return c


# Non-overlapping: choose rules on 2025, check on 2026 H1, then the live window.
PERIODS = {"2025 (choose)": ("2025-01-01", "2025-12-31"),
           "2026 H1 (check)": ("2026-01-01", "2026-06-14"),
           "live window": ("2026-06-15", "2026-09-18")}


@dataclass
class Spec:
    name: str
    select: str = "first_pass"                 # "live" | "first_pass"
    mask: callable = None                      # extra filter on tradeable rows (applied before 'first')
    entry: str = "market"                      # "market" | "limit"
    limit_bars: int = 6
    exit: ExitRule = field(default_factory=lambda: LIVE_EXIT)


def pick(feat: pd.DataFrame, cand: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    if spec.select == "live":
        base = cand[cand.live_take_c == True]
        base = base.merge(feat[["date", "scan", "symbol", "runup_pct", "nifty_now_pct", "vwap_pct"]],
                          on=["date", "scan", "symbol"], how="left")
    else:
        base = feat
    if spec.mask is not None:
        base = base[spec.mask(base)]
    return base.sort_values(["date", "scan", "rank"]).groupby("date", as_index=False).head(1)


def run(feat: pd.DataFrame, cand: pd.DataFrame, specs: list[Spec], notional: float = 200_000,
        periods: dict | None = None) -> tuple[pd.DataFrame, dict]:
    periods = periods or PERIODS
    rows, trades = [], {}
    for s in specs:
        t = trades_from_rows(pick(feat, cand, s), s.entry, s.exit, notional, limit_window_bars=s.limit_bars)
        trades[s.name] = t
        for pname, (a, b) in periods.items():
            tt = t[(t.date >= a) & (t.date <= b)] if len(t) else t
            rows.append({"period": pname, **summarize(tt, s.name)})
    R = pd.DataFrame(rows)
    return R, trades


def pivot(R: pd.DataFrame, value: str = "net_rs") -> pd.DataFrame:
    P = R.pivot_table(index="policy", columns="period", values=value, aggfunc="first", sort=False)
    T = R.pivot_table(index="policy", columns="period", values="trades", aggfunc="first", sort=False)
    W = R.pivot_table(index="policy", columns="period", values="win_pct", aggfunc="first", sort=False)
    out = pd.concat({value: P, "trades": T, "win%": W}, axis=1)
    return out

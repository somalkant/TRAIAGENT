"""Tables used by notebooks/05_live_vs_backtest_gap_LONG.ipynb (kept here so the notebook stays readable)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import CHECKPOINT_DIR, TRADE_LOG_DIR

ROOT = Path(__file__).resolve().parent.parent

# Live config changes during the sample (git log on ec2-deploy) — the live record mixes all of these.
CONFIG_ERAS = [
    ("2026-06-15", "early build: re-anchored entries to live price (chased), 15:15 exit"),
    ("2026-07-14", "drift gate 0.30% + 30-min expiry + trailing profit-lock"),
    ("2026-07-20", "ATR-normalised sizing"),
    ("2026-07-23", "stop-viability gate"),
    ("2026-07-29", "ride past target once locked"),
    ("2026-07-30", "final stop cap 1.5%"),
    ("2026-07-31", "fill gate (cross the spread) + square-off 14:50"),
    ("2026-09-06", "stop cap tightened to 1.0%"),
]


def live_long() -> pd.DataFrame:
    L = pd.read_csv(TRADE_LOG_DIR / "live_paper_trades.csv", parse_dates=["date"])
    L = L[L.direction == "LONG"].copy()
    L["month"] = L.date.dt.to_period("M").astype(str)
    L["notional"] = L.entry_price * L.quantity
    L["ret_pct"] = L.pnl_rs / L.notional * 100
    L["era"] = pd.cut(L.date, [pd.Timestamp(d) for d, _ in CONFIG_ERAS] + [pd.Timestamp("2027-01-01")],
                      right=False, labels=[f"{d} {t}" for d, t in CONFIG_ERAS])
    return L


def by(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df.groupby(col, observed=True).agg(
        trades=("pnl_rs", "size"), win_pct=("pnl_rs", lambda x: round(100 * (x > 0).mean(), 1)),
        net_rs=("pnl_rs", lambda x: round(x.sum())), avg_ret_pct=("ret_pct", lambda x: round(x.mean(), 3)))


def live_candle_health() -> pd.DataFrame:
    """Share of live-built 5-min bars (to 11:00) with zero volume, per session."""
    rows = []
    for f in sorted(CHECKPOINT_DIR.glob("live_candles_2026-*.json")):
        j = json.loads(f.read_text())
        tot = zero = 0
        for bars in j["symbols"].values():
            for b in bars:
                if b["datetime"][11:16] <= "11:00":
                    tot += 1
                    zero += b["volume"] == 0
        rows.append(dict(date=j["date"], bars=tot, zero_volume_pct=round(100 * zero / max(tot, 1), 1)))
    return pd.DataFrame(rows)


def causality_table(path: Path | None = None) -> pd.DataFrame:
    R = pd.read_csv(path or ROOT / "reports" / "gap_analysis" / "causality_audit.csv")
    fired = R[~R.cls.isin(["nofire", "error_full"])]
    tab = pd.crosstab(fired.strategy, fired.cls)
    for c in ["exact", "delayed", "unstable", "never", "late_or_untimed", "nofire_full_but_trunc_fired"]:
        if c not in tab:
            tab[c] = 0
    tab["fired"] = tab[["exact", "delayed", "unstable", "never", "late_or_untimed"]].sum(axis=1)
    denom = tab[["exact", "delayed", "unstable", "never"]].sum(axis=1).clip(lower=1)
    tab["causal_%"] = (100 * tab.exact / denom).round(0)
    tab["median_backdate_min"] = R[R.cls == "delayed"].groupby("strategy").lag.median()
    return tab.fillna(0)[["fired", "exact", "delayed", "median_backdate_min", "unstable", "never",
                          "late_or_untimed", "causal_%"]].sort_values("causal_%")


def bt_pick_at_signal_time(bt: pd.DataFrame, cand: pd.DataFrame) -> pd.DataFrame:
    """For every backtest pick: what did the stock look like at the first scan that could have seen
    its signal (signal_time + 5 min), using only votes cast by then?"""
    idx = cand.set_index(["date", "scan", "symbol"])
    idx = idx[~idx.index.duplicated()]
    rows = []
    for r in bt.itertuples():
        h, m = map(int, r.signal_time.split(":"))
        scan = f"{(h * 60 + m + 5) // 60:02d}:{(h * 60 + m + 5) % 60:02d}"
        k = (r.date, scan, r.symbol)
        if k in idx.index:
            c = idx.loc[k]
            rows.append(dict(date=r.date, symbol=r.symbol, scan=scan, full_day_score=r.raw_score,
                             full_day_agreeing=r.agreeing, score_then=c.raw_score, agreeing_then=c.agreeing,
                             quality_then=bool(c.quality_ok) if pd.notna(c.quality_ok) else False,
                             reason_then=c.quality_reason if isinstance(c.quality_reason, str) else "",
                             in_top50_then=True))
        else:
            rows.append(dict(date=r.date, symbol=r.symbol, scan=scan, full_day_score=r.raw_score,
                             full_day_agreeing=r.agreeing, score_then=np.nan, agreeing_then=np.nan,
                             quality_then=False, reason_then="not a scored candidate at that scan",
                             in_top50_then=False))
    return pd.DataFrame(rows)

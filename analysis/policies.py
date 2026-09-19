"""
Turn replay output (analysis.replay) into trades under different entry/selection/exit policies.

A policy = (which candidate each day) x (how you enter) x (how you exit). Every policy is
priced at the same fixed notional (default Rs 2,00,000 — the planned live capital) with the
same cost model, so policies are comparable trade for trade.

Candidate selection
  bt          the backtest's own pick (full-day hindsight)            -> bt table
  live        live's first TAKE (all live gates)                       -> cand.live_take
  first_pass  first candidate that passed the quality filters,
              ignoring the live-only drift / viability / RR gates     -> cand rows
Entry
  bt_level    at the strategy level, on the signal bar (backtest fiction)
  market      at the price when the scan decides (bar-mid at scan+3min)
  limit       buy limit at the strategy level, resting from the scan bar for N bars
Exit          see analysis.simulate.run_exit (stop rule / target rule / trailing lock)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.simulate import day_bars, bar_index, run_exit, limit_fill, pnl

REPLAY_DIR = Path(__file__).resolve().parent.parent / "reports" / "gap_analysis" / "replay"


def load_replay(start: str | None = None, end: str | None = None,
                last_scan: str = "11:00") -> tuple[pd.DataFrame, pd.DataFrame]:
    bt = pd.concat([pd.read_parquet(f) for f in sorted(REPLAY_DIR.glob("bt_*.parquet"))], ignore_index=True)
    cand = pd.concat([pd.read_parquet(f) for f in sorted(REPLAY_DIR.glob("cand_*.parquet"))], ignore_index=True)
    for df in (bt, cand):
        df["date"] = pd.to_datetime(df["date"])
    if start:
        bt, cand = bt[bt.date >= start], cand[cand.date >= start]
    if end:
        bt, cand = bt[bt.date <= end], cand[cand.date <= end]
    cand = cand[cand.scan <= last_scan]           # the first blocks scanned to 13:55; keep it uniform
    cand = cand.sort_values(["date", "scan", "rank"]).reset_index(drop=True)
    return bt.sort_values("date").reset_index(drop=True), regate(cand)


def regate(cand: pd.DataFrame) -> pd.DataFrame:
    """Re-run live's gate chain on a CAUSAL decision price.

    The replay stored `px` = mid of the scan bar B, (open+close)/2. That is an unbiased *entry* price,
    but bar B's close only exists at B+5 — after live decides at ~B+3 — so any gate or filter that
    SELECTS on it peeks at the future (it prefers bars that closed strong). Every price-based gate is
    therefore recomputed here on p_dec = bar B's open (known before the decision). `px` stays the entry
    price. Columns added: p_dec, drift_dec, gate_c, live_take_c."""
    from config.settings import (SIGNAL_EXPIRY_MIN, MAX_STOP_DISTANCE_PCT, MIN_TARGET_DISTANCE_PCT,
                                 ENTRY_DRIFT_GATE_PCT, MIN_RISK_REWARD, MIN_STOP_ATR_RATIO,
                                 MIN_STOP_ATR_RATIO_OPEN, STOP_VIABILITY_OPEN_UNTIL)
    c = cand.copy()
    c["p_dec"] = c.px_open.fillna(c.px) if "px_open" in c else c.px
    c["drift_dec"] = (c.p_dec - c.level) / c.level * 100
    now = c.scan.str[:2].astype(int) * 60 + c.scan.str[3:].astype(int) + 3
    stop_d = (c.level - c.stop0).abs() / c.level * 100
    tgt_d = (c.target0 - c.level).abs() / c.level * 100
    rr = (c.target0 - c.p_dec) / (c.p_dec - c.stop0)
    floor = np.where(now < STOP_VIABILITY_OPEN_UNTIL.hour * 60 + STOP_VIABILITY_OPEN_UNTIL.minute,
                     MIN_STOP_ATR_RATIO_OPEN, MIN_STOP_ATR_RATIO)
    ratio = ((c.p_dec - c.stop0) / c.p_dec * 100) / c.atr
    no_driver = c.driver.isna()
    c["gate_c"] = np.select(
        [no_driver,
         c.sig_age > SIGNAL_EXPIRY_MIN,
         (stop_d > MAX_STOP_DISTANCE_PCT) | (tgt_d < MIN_TARGET_DISTANCE_PCT),
         c.quality_ok != True,
         (c.p_dec <= c.stop0) | (c.p_dec >= c.target0),
         c.drift_dec >= ENTRY_DRIFT_GATE_PCT,
         rr < MIN_RISK_REWARD,
         ratio.notna() & (ratio < floor)],
        ["NO_DRIVER", "SKIP_STALE", "SKIP_GEOMETRY", "FAIL_QUALITY", "SKIP_DEAD", "SKIP_DRIFT",
         "SKIP_RR", "SKIP_VIABILITY"], default="TAKE")
    first_take = c[c.gate_c == "TAKE"].groupby("date").head(1).index
    c["live_take_c"] = False
    c.loc[first_take, "live_take_c"] = True
    return c


TRADEABLE_GATES = ["SKIP_STALE", "SKIP_GEOMETRY", "NO_DRIVER", "FAIL_QUALITY", "SKIP_DEAD"]


def tradeable(c: pd.DataFrame) -> pd.Series:
    """Passed everything live checks BEFORE its price gates (expiry, geometry, quality) and the price
    at the decision is still between stop and target — i.e. the stock live 'wanted'."""
    return ~c.gate_c.isin(TRADEABLE_GATES)


# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExitRule:
    stop: str = "cap1"            # "strategy" | "cap1" (strategy stop, capped at 1%) | "fixed:<pct>"
    target: str = "strategy"      # "strategy" | "fixed:<pct>" | "none"
    trail: bool = True            # live profit-lock: +1% trigger, 0.5% trail, ride past target
    trigger_pct: float = 1.0
    trail_pct: float = 0.5
    ambiguous: str = "stop"
    squareoff: int = 14 * 60 + 45     # bar label whose close is the exit (14:45 close = 2:50 PM)
    gap_fill: bool = True
    time_exit_at: str = "close"

    def levels(self, entry: float, stop0: float, target0: float) -> tuple[float, float | None]:
        if self.stop == "strategy":
            stop = stop0
        elif self.stop == "cap1":
            stop = max(stop0, entry * 0.99)
        else:
            stop = entry * (1 - float(self.stop.split(":")[1]) / 100)
        if self.target == "strategy":
            tgt = target0
        elif self.target == "none":
            tgt = None
        else:
            tgt = entry * (1 + float(self.target.split(":")[1]) / 100)
        return stop, tgt


LIVE_EXIT = ExitRule()                                            # what live runs today
# backtester.engine._simulate_outcome: target checked before stop, stops fill at the level even
# through a gap, square-off at the OPEN of the 15:15 bar
BT_EXIT = ExitRule(stop="strategy", target="strategy", trail=False, ambiguous="target",
                   squareoff=15 * 60 + 15, gap_fill=False, time_exit_at="open")
REAL_BT_EXIT = ExitRule(stop="strategy", target="strategy", trail=False, ambiguous="stop")


def _trade(date, symbol, entry_idx, entry, stop0, target0, rule: ExitRule, notional, meta,
           start_next_bar: bool = True) -> dict | None:
    bars = day_bars(symbol, date.date() if hasattr(date, "date") else date)
    stop, tgt = rule.levels(entry, stop0, target0)
    if stop >= entry or (tgt is not None and tgt <= entry):
        return None
    x = run_exit(bars, entry_idx, entry, stop, tgt, trail=rule.trail, trigger_pct=rule.trigger_pct,
                 trail_pct=rule.trail_pct, ambiguous=rule.ambiguous, squareoff=rule.squareoff,
                 gap_fill=rule.gap_fill, time_exit_at=rule.time_exit_at, start_next_bar=start_next_bar)
    p, q = pnl(entry, x.price, notional=notional)
    return dict(date=date, symbol=symbol, entry=entry, stop=stop, target=tgt, exit=x.price,
                exit_time=x.time, exit_reason=x.reason, mfe_pct=x.mfe_pct, mae_pct=x.mae_pct,
                pnl=p, qty=q, ret_pct=(x.price - entry) / entry * 100, **meta)


def trades_from_rows(rows: pd.DataFrame, entry: str, rule: ExitRule, notional: float = 200_000,
                     limit_window_bars: int = 6) -> pd.DataFrame:
    """rows: one candidate row per trade (date, scan, symbol, level, stop0, target0, px, ...)."""
    out = []
    for r in rows.itertuples():
        bars = day_bars(r.symbol, r.date.date())
        if bars.empty:
            continue
        meta = dict(scan=r.scan, driver=getattr(r, "driver", None), signal_time=getattr(r, "signal_time", None),
                    level=r.level, drift_pct=getattr(r, "drift_dec", np.nan), gate=getattr(r, "gate_c", None),
                    raw_score=getattr(r, "raw_score", np.nan), agreeing=getattr(r, "agreeing", np.nan),
                    atr=getattr(r, "atr", np.nan), rank=getattr(r, "rank", np.nan))
        bi = bar_index(bars, r.scan)
        if bi is None:
            continue
        if entry in ("market", "market_close"):
            pdec = float(getattr(r, "p_dec", r.px))
            if pdec <= r.stop0 or pdec >= r.target0:
                continue
            # entry: bar-mid (unbiased when not selected on); 'market_close' = pessimistic bound
            px = float(r.px) if entry == "market" else float(getattr(r, "px_close", r.px))
            if px <= r.stop0:
                continue
            t = _trade(r.date, r.symbol, bi, px, r.stop0, r.target0, rule, notional, {**meta, "fill": "market"})
        elif entry == "limit":
            pdec = float(getattr(r, "p_dec", r.px))
            if pdec <= r.level:                                   # already at/below the level: fills now
                fi, fpx = bi, pdec
            else:
                f = limit_fill(bars, bi + 1, float(r.level), limit_window_bars)
                if f is None:
                    continue
                fi, fpx = f
            # the fill bar is a down-move by construction: check its low against the stop too
            t = _trade(r.date, r.symbol, fi, fpx, r.stop0, r.target0, rule, notional,
                       {**meta, "fill": f"limit@{bars.iloc[fi].m // 60:02d}:{bars.iloc[fi].m % 60:02d}"},
                       start_next_bar=False)
        else:
            raise ValueError(entry)
        if t:
            out.append(t)
    return pd.DataFrame(out)


def bt_trades(bt: pd.DataFrame, entry: str, rule: ExitRule, notional: float = 200_000) -> pd.DataFrame:
    """The backtest's own picks, re-priced. entry='bt_level' reproduces the backtest's fiction;
    entry='market' enters at the first scan that could have seen the signal (signal bar + 5 min)."""
    out = []
    for r in bt.itertuples():
        bars = day_bars(r.symbol, r.date.date())
        si = bar_index(bars, r.signal_time)
        if si is None:
            continue
        meta = dict(driver=r.driver, signal_time=r.signal_time, level=r.level, raw_score=r.raw_score,
                    agreeing=r.agreeing, bt_reported_pnl=r.pnl_rs, bt_exit_reason=r.exit_reason)
        if entry == "bt_level":
            t = _trade(r.date, r.symbol, si, float(r.level), r.stop, r.target, rule, notional, {**meta, "fill": "level"})
        elif entry == "market":
            ei = si + 1                                  # the scan at signal_time+5 decides in this bar
            if ei >= len(bars):
                continue
            b = bars.iloc[ei]
            px = float((b.open + b.close) / 2)
            if px <= r.stop or px >= r.target:
                continue
            t = _trade(r.date, r.symbol, ei, px, r.stop, r.target, rule, notional,
                       {**meta, "fill": "market", "drift_pct": (px - r.level) / r.level * 100})
        else:
            raise ValueError(entry)
        if t:
            out.append(t)
    return pd.DataFrame(out)


# ─────────────────────────────────────────────────────────────────────────────
# candidate selectors

def pick_live(cand: pd.DataFrame) -> pd.DataFrame:
    return cand[cand.live_take_c == True].groupby("date", as_index=False).head(1)


def pick_first_pass(cand: pd.DataFrame, before: str | None = None, extra: pd.Series | None = None) -> pd.DataFrame:
    """First candidate per day that live 'wanted' (passed expiry/geometry/quality, price still between
    stop and target), ignoring live's price gates (drift / RR / viability)."""
    m = tradeable(cand)
    if before:
        m &= cand.scan < before
    if extra is not None:
        m &= extra
    return cand[m].groupby("date", as_index=False).head(1)


def summarize(t: pd.DataFrame, label: str = "") -> dict:
    if t is None or len(t) == 0:
        return dict(policy=label, trades=0)
    eq = t.sort_values("date").pnl.cumsum()
    net_pct = t.pnl / (t.entry * t.qty) * 100            # per-trade return after costs
    se = net_pct.std(ddof=1) / np.sqrt(len(t)) if len(t) > 1 else np.nan
    return dict(policy=label, trades=len(t), win_pct=round(100 * (t.pnl > 0).mean(), 1),
                net_rs=round(t.pnl.sum()), avg_rs=round(t.pnl.mean()),
                avg_net_pct=round(net_pct.mean(), 3), t_stat=round(net_pct.mean() / se, 2) if se else np.nan,
                max_dd_rs=round((eq - eq.cummax()).min()),
                stop_pct=round(100 * (t.exit_reason == "STOP_HIT").mean(), 1))

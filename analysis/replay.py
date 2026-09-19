"""
Day-by-day replay of the LONG entry decision on identical historical data, two ways:

  BACKTEST (as-is)  backtester.engine._find_best_candidate on FULL-DAY signals, exactly as
                    run_testing.py does it: rank on the whole day's vote count, driver chosen
                    from the whole day, entry at the strategy's level at signal_time, exits
                    checked target-before-stop, square-off 15:15.

  CAUSAL (live)     what live/live_engine.py would have seen at every 5-min scan: only bars
                    that had closed, the same ranking and quality filters, then the live-only
                    gates in the same order (30-min signal expiry, stop/target distance,
                    price already past stop/target, 0.30% drift gate, RR re-check, stop
                    viability vs ATR), 1% stop cap. Every candidate walked is recorded with
                    every gate's verdict, so alternative policies can be evaluated offline.

Nothing in live/, backtester/ or strategies/ is modified; their functions are imported.

Performance notes (all validated in notebooks/05, section 2):
  * 24 of the LONG-capable strategies are causal and fire once: their signal on bars up to
    k equals the full-day signal once k >= signal_time. They are computed once per day and
    revealed at signal_time. The 7 in PER_BAR back-date or change their signals and are
    recomputed on truncated bars at every scan.
  * Bearish-only strategies never cast a LONG vote and are skipped.
  * Strategies get the last HIST_DAYS trading days of history (longest lookback is 60 daily
    bars) — verified to give identical signals to the full history.
  * Price at scan time = midpoint of the 5-min bar in progress when the ~3-minute live scan
    finishes (calibrated on the 59 real live fills: median error 0.000%).
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import (
    STOCKS_DIR, INDEX_DIR, CHECKPOINT_DIR,
    AGREEMENT_MIN_LIFETIME_WR_LONG, MIN_RISK_REWARD, ENTRY_DRIFT_GATE_PCT, SIGNAL_EXPIRY_MIN,
    MAX_STOP_DISTANCE_PCT, MIN_TARGET_DISTANCE_PCT, MAX_POSITION_SIZE, ATR_RISK_BUDGET_RS,
    MIN_STOP_ATR_RATIO, MIN_STOP_ATR_RATIO_OPEN, STOP_VIABILITY_OPEN_UNTIL, STOP_CAP_PCT,
)
from strategies import ALL_STRATEGIES
from strategies.base import Signal
from backtester import engine as bt
from backtester.composite_scorer import long_composite_score, count_agreeing_filtered
from backtester.quality_filter import passes_all_filters
from backtester.position_sizer import position_size
from weights.regime import get_regime_modifiers, get_direction_bias
from watchlist.pre_filter import PreMarketFilter
from analysis.fast_perbar import adx_signals, intraday_struct_signals

HIST_DAYS = 70                  # trading days of history handed to strategies / pre-filter
SCAN_LATENCY_MIN = 3            # live scan finishes ~184 s after the bar boundary
FIRST_SCAN = time(9, 20)
LAST_SCAN = time(13, 55)        # live stops looking for entries at NO_ENTRY_AFTER 14:00

# Recomputed on truncated bars every scan: these back-date signals (PIN-BAR, SR-BREAK, EMA-CROSS,
# VWAP-REV, ORB-15/30), re-stamp the last bar (INTRADAY-STRUCT), or vote on the LAST bar's ADX
# (ADX-FILTER — on a full day that is the 15:25 ADX, i.e. how the day ended).
PER_BAR = {"PIN-BAR", "SR-BREAK", "EMA-CROSS", "VWAP-REV", "ORB-30", "ORB-15", "INTRADAY-STRUCT", "ADX-FILTER"}
LONG_CAPABLE = [s for s in ALL_STRATEGIES if s.category != "bearish"]
EXACT = [s for s in LONG_CAPABLE if s.name not in PER_BAR]
# ADX-FILTER and INTRADAY-STRUCT are evaluated for every bar in one pass (analysis.fast_perbar,
# verified identical to per-bar generate_signal calls); the rest are called per scan.
_FAST = {"ADX-FILTER", "INTRADAY-STRUCT"}
PERBAR = [s for s in LONG_CAPABLE if s.name in PER_BAR and s.name not in _FAST]
_NO = {s.name: Signal(strategy=s.name, direction=0) for s in ALL_STRATEGIES}


# ─────────────────────────────────────────────────────────────────────────────
# data
# ─────────────────────────────────────────────────────────────────────────────

def _naive_ist(s: pd.Series) -> pd.Series:
    """2024-25 parquets are tz-aware (+05:30), 2026 ones are naive IST — normalise to naive IST."""
    s = pd.to_datetime(s)
    if s.dt.tz is not None:
        s = s.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return s


def load_symbol(symbol: str, start: date, end: date) -> pd.DataFrame:
    parts = []
    for y in range(start.year, end.year + 1):
        f = STOCKS_DIR / str(y) / f"{symbol}.parquet"
        if f.exists():
            d = pd.read_parquet(f, columns=["datetime", "open", "high", "low", "close", "volume"])
            d["datetime"] = _naive_ist(d["datetime"])
            parts.append(d)
    if not parts:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    d = (pd.concat(parts).drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True))
    day = (d.datetime.values.astype("datetime64[D]").astype("int64") + 719163).astype("int32")  # date.toordinal()
    keep = (day >= start.toordinal()) & (day <= end.toordinal())
    d = d[keep].reset_index(drop=True)
    d["_d"] = day[keep]
    return d


def load_nifty(start: date, end: date) -> pd.DataFrame:
    parts = []
    for y in range(start.year, end.year + 1):
        f = INDEX_DIR / str(y) / "NIFTY50.parquet"
        if f.exists():
            d = pd.read_parquet(f); d["datetime"] = _naive_ist(d["datetime"]); parts.append(d)
    d = pd.concat(parts).drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    return d[(d.datetime.dt.date >= start) & (d.datetime.dt.date <= end)].reset_index(drop=True)


def universe() -> list[str]:
    return sorted(p.stem for p in (STOCKS_DIR / "2026").glob("*.parquet"))


def trading_days(start: date, end: date) -> list[date]:
    n = load_nifty(start, end)
    return sorted(n.datetime.dt.date.unique())


def load_weights() -> dict:
    """Exactly what live loads: checkpoints/wf5_weights.json."""
    return bt._load_weights(CHECKPOINT_DIR / "wf5_weights.json")


def saved_watchlist(d: date) -> list[str] | None:
    f = CHECKPOINT_DIR / f"watchlist_{d}.json"
    if not f.exists():
        return None
    w = json.loads(f.read_text())["watchlist"]
    return [e["symbol"] if isinstance(e, dict) else e for e in w]


class Block:
    """All stock data a worker needs for a contiguous block of trading days."""

    def __init__(self, days: list[date], symbols: list[str]):
        self.days = days
        start = days[0] - timedelta(days=int(HIST_DAYS * 1.6) + 10)
        self.data = {}
        for s in symbols:
            d = load_symbol(s, start, days[-1])
            if len(d):
                self.data[s] = d
        self.nifty = load_nifty(start, days[-1])

    def split(self, sym: str, d: date) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = self.data.get(sym)
        if df is None:
            return pd.DataFrame(), pd.DataFrame()
        o = d.toordinal()
        today = df[df._d == o].drop(columns="_d").reset_index(drop=True)
        hist = df[df._d < o]
        hdays = np.unique(hist._d.values)
        if len(hdays) > HIST_DAYS:
            hist = hist[hist._d >= hdays[-HIST_DAYS]]
        return today, hist.drop(columns="_d").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# per-day context
# ─────────────────────────────────────────────────────────────────────────────

def _turnover_cr(hist: pd.DataFrame) -> float:
    """live/live_engine._estimate_turnover and engine._estimate_turnover: median of last 20 days."""
    if hist.empty:
        return 0.0
    recent = hist.tail(20 * 75)
    by_day = (recent.close * recent.volume).groupby(recent.datetime.dt.date).sum() / 1e7
    return float(by_day.median()) if len(by_day) else 0.0


def _atr_pct(hist: pd.DataFrame, period: int = 14) -> float | None:
    """live_engine._atr_pct_from_history, reimplemented on the same inputs."""
    if hist.empty:
        return None
    daily = hist.groupby(hist.datetime.dt.date).agg(high=("high", "max"), low=("low", "min"),
                                                     close=("close", "last"))
    if len(daily) < period + 1:
        return None
    pc = daily.close.shift(1)
    tr = pd.concat([daily.high - daily.low, (daily.high - pc).abs(), (daily.low - pc).abs()], axis=1).max(axis=1)
    ref = float(daily.close.iloc[-1])
    return float(tr.tail(period).mean() / ref * 100) if ref > 0 else None


def _hm(t: str) -> int:
    h, m = map(int, t.split(":")[:2])
    return h * 60 + m


def _fmt(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# the replay
# ─────────────────────────────────────────────────────────────────────────────

def replay_day(blk: Block, d: date, weights: dict, all_symbols: list[str],
               use_saved_watchlist: bool = True, last_scan: time = LAST_SCAN) -> dict:
    # ── watchlist (pre-market, history only) ───────────────────────────────
    wl = saved_watchlist(d) if use_saved_watchlist else None
    wl_src = "saved"
    if wl is None:
        wl_src = "prefilter"
        hist_all = {}
        for s in all_symbols:
            _, h = blk.split(s, d)
            if len(h):
                hist_all[s] = h
        wl = [e["symbol"] for e in PreMarketFilter().build(d, hist_all)]

    nifty_today = blk.nifty[blk.nifty.datetime.dt.date == d].reset_index(drop=True)
    nprev = blk.nifty[blk.nifty.datetime.dt.date < d]
    nifty_pct = 0.0
    if len(nifty_today) and len(nprev):
        pc = float(nprev.close.iloc[-1])
        nifty_pct = round((float(nifty_today.open.iloc[0]) - pc) / pc * 100, 3) if pc > 0 else 0.0
    regime_mods = get_regime_modifiers(weights, vix=15.0)
    long_bias, _ = get_direction_bias(15.0, nifty_pct)

    # ── per-stock inputs + full-day signals ────────────────────────────────
    ctx = {}
    for s in wl:
        today, hist = blk.split(s, d)
        if today.empty or hist.empty:
            continue
        prev = bt._get_prev_day_ohlc(hist, d)
        full = {}
        for st in LONG_CAPABLE:
            try:
                full[st.name] = st.generate_signal(today, hist, prev, nifty_today, d)
            except Exception:
                full[st.name] = _NO[st.name]
        labels = today.datetime.dt.strftime("%H:%M").tolist()
        ctx[s] = dict(today=today, hist=hist, prev=prev, full=full,
                      fast={"ADX-FILTER": adx_signals(today, hist), "INTRADAY-STRUCT": intraday_struct_signals(today)},
                      turnover=_turnover_cr(hist), atr=_atr_pct(hist),
                      mins=np.array([_hm(x) for x in labels]), idx={lab: i for i, lab in enumerate(labels)})

    # ── BACKTEST pick, verbatim engine logic ───────────────────────────────
    bt_pick = None
    if ctx:
        scores = {}
        for s, c in ctx.items():
            raw = long_composite_score(c["full"], weights, regime_mods)
            scores[s] = (raw, raw * long_bias)
        rec = bt._find_best_candidate(
            direction=+1, stock_scores=scores, stock_signals={s: c["full"] for s, c in ctx.items()},
            all_data={s: c["today"] for s, c in ctx.items()}, trade_date=d,
            daily_turnover={s: c["turnover"] for s, c in ctx.items()}, weights=weights,
            freeze_weights=True, nifty_pct=nifty_pct)
        if rec:
            sg = rec["signal"]
            bt_pick = dict(date=d, symbol=rec["symbol"], driver=sg["strategy"], signal_time=sg["signal_time"],
                           level=sg["entry"], stop=sg["stop"], target=sg["target"], rr=sg["rr"],
                           raw_score=rec["raw_score"], agreeing=rec["agreeing"],
                           pred=rec["predicted_win_pct"], shares=rec["shares"],
                           position_rs=rec["position_rs"], exit_reason=rec["outcome"]["exit_reason"],
                           exit_price=rec["outcome"]["exit_price"], exit_time=rec["outcome"]["exit_time"],
                           pnl_rs=rec["pnl_rs"], wl_src=wl_src, nifty_pct=nifty_pct)

    # ── CAUSAL scans ───────────────────────────────────────────────────────
    rows = []
    t0, t1 = FIRST_SCAN.hour * 60 + FIRST_SCAN.minute, last_scan.hour * 60 + last_scan.minute
    viab_open_until = STOP_VIABILITY_OPEN_UNTIL.hour * 60 + STOP_VIABILITY_OPEN_UNTIL.minute
    for B in range(t0, t1 + 1, 5):
        closed = B - 5                      # last closed bar label visible to this scan
        now = B + SCAN_LATENCY_MIN          # when the scan's decisions are made
        sig_at, scored = {}, []
        nt = nifty_today[nifty_today.datetime.dt.hour * 60 + nifty_today.datetime.dt.minute <= closed]
        for s, c in ctx.items():
            n_closed = int((c["mins"] <= closed).sum())
            if n_closed == 0:
                continue
            today_t = c["today"].iloc[:n_closed]
            sigs = {}
            for st in EXACT:
                f = c["full"][st.name]
                if f.direction != 0 and not f.signal_time:
                    sigs[st.name] = f        # history-only vote (DAILY-BIAS): known before the open
                elif f.direction != 0 and _hm(f.signal_time) <= closed:
                    sigs[st.name] = f
                else:
                    sigs[st.name] = _NO[st.name]
            for st in PERBAR:
                try:
                    sigs[st.name] = st.generate_signal(today_t, c["hist"], c["prev"], nt, d)
                except Exception:
                    sigs[st.name] = _NO[st.name]
            for name in _FAST:
                sigs[name] = c["fast"][name][n_closed - 1]
            raw = long_composite_score(sigs, weights, regime_mods)
            sig_at[s] = (sigs, today_t)
            scored.append((s, raw, raw * long_bias))
        scored.sort(key=lambda x: x[2], reverse=True)

        taken = False
        for rank, (s, raw, adj) in enumerate(scored[:50], 1):
            if raw <= 0:
                break
            sigs, today_t = sig_at[s]
            c = ctx[s]
            best = bt._best_signal(sigs, direction=+1)
            row = dict(date=d, scan=_fmt(B), rank=rank, symbol=s, raw_score=raw, adj_score=adj,
                       n_bars=len(today_t), wl_src=wl_src, nifty_pct=nifty_pct)
            if best is None:
                row["gate"] = "NO_DRIVER"; rows.append(row); continue
            best = dataclasses.replace(best)          # never mutate the cached signal
            level, stop0, target0 = float(best.entry), float(best.stop), float(best.target)
            agreeing = count_agreeing_filtered(sigs, +1, bt._LIFETIME_WR, AGREEMENT_MIN_LIFETIME_WR_LONG)
            pred = bt._predicted_win_pct(sigs, weights, bt._LIFETIME_WR, direction=+1)
            age = max(0.0, now - _hm(best.signal_time)) if best.signal_time else None
            row.update(driver=best.strategy, signal_time=best.signal_time, level=level, stop0=stop0,
                       target0=target0, rr0=best.rr, agreeing=agreeing, pred=pred, sig_age=age,
                       turnover=c["turnover"], atr=c["atr"],
                       n_long_votes=sum(1 for v in sigs.values() if v.direction == 1))
            # price when the scan decides: midpoint of the bar in progress at `now`
            i_now = c["idx"].get(_fmt(B))
            if i_now is not None:
                bar = c["today"].iloc[i_now]
                px = float((bar.open + bar.close) / 2)
                row.update(px_open=float(bar.open), px_close=float(bar.close))
            else:
                px = float(today_t.close.iloc[-1])
            row["px"] = px
            row["drift_pct"] = (px - level) / level * 100 if level > 0 else np.nan

            # ── the live walk, gate by gate (live_engine._find_live_candidate order) ──
            gate = None
            q_ok, q_reason = passes_all_filters(signal=best, today_5min=today_t,
                                                daily_turnover_crore=c["turnover"],
                                                strategies_agreeing=agreeing, composite_score=raw,
                                                predicted_win_pct=pred, nifty_pct_change=nifty_pct)
            row.update(quality_ok=q_ok, quality_reason=q_reason)
            stop_d = abs(level - stop0) / level * 100 if level else 0
            tgt_d = abs(target0 - level) / level * 100 if level else 0
            if age is not None and age > SIGNAL_EXPIRY_MIN:
                gate = "SKIP_STALE"
            elif stop_d > MAX_STOP_DISTANCE_PCT or tgt_d < MIN_TARGET_DISTANCE_PCT:
                gate = "SKIP_GEOMETRY"
            elif not q_ok:
                gate = "FAIL_QUALITY"
            elif px <= stop0 or px >= target0:
                gate = "SKIP_DEAD"
            elif row["drift_pct"] >= ENTRY_DRIFT_GATE_PCT:
                gate = "SKIP_DRIFT"
            else:
                rr_live = (target0 - px) / (px - stop0) if px > stop0 else -1
                row["rr_live"] = rr_live
                if rr_live < MIN_RISK_REWARD:
                    gate = "SKIP_RR"
                else:
                    atr = c["atr"]
                    ratio = ((px - stop0) / px * 100) / atr if atr else None
                    row["stop_atr_ratio"] = ratio
                    floor = MIN_STOP_ATR_RATIO_OPEN if now < viab_open_until else MIN_STOP_ATR_RATIO
                    if ratio is not None and ratio < floor:
                        gate = "SKIP_VIABILITY"
                    else:
                        gate = "TAKE"
            row["gate"] = gate
            # what live would have done if this candidate were taken (computed for every
            # quality-passing candidate, so skip-policies can be priced later)
            conv_mult, conv_tier = bt._conviction_multiplier(best.strategy, +1)
            stop_live = stop0
            if px > 0 and (px - stop0) / px * 100 > STOP_CAP_PCT:
                stop_live = round(px * (1 - STOP_CAP_PCT / 100), 2)
            rs, sh = position_size(px, stop0, conv_mult, atr_pct=c["atr"],
                                   atr_risk_rs=ATR_RISK_BUDGET_RS, max_notional=MAX_POSITION_SIZE)
            row.update(stop_live=stop_live, shares_live=sh, notional_live=rs, conv_tier=conv_tier)
            if gate == "TAKE" and not taken:
                row["live_take"] = True
                taken = True
            rows.append(row)
    return dict(bt_pick=bt_pick, rows=rows, wl_size=len(wl), wl_src=wl_src, n_ctx=len(ctx))


def run_block(days: list[date], use_saved_watchlist: bool = True, out_dir: Path | None = None,
              tag: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    import warnings
    warnings.filterwarnings("ignore")
    weights = load_weights()
    syms = universe()
    blk = Block(days, syms)
    bts, rows = [], []
    for d in days:
        r = replay_day(blk, d, weights, syms, use_saved_watchlist=use_saved_watchlist,
                       last_scan=LAST_SCAN)          # read the module global at call time
        if r["bt_pick"]:
            bts.append(r["bt_pick"])
        rows.extend(r["rows"])
    B, C = pd.DataFrame(bts), pd.DataFrame(rows)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        B.to_parquet(out_dir / f"bt_{tag}.parquet")
        C.to_parquet(out_dir / f"cand_{tag}.parquet")
    return B, C

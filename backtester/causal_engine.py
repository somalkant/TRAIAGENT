"""
Causal (left-to-right) intraday LONG backtest — the live system's decision logic, run on history the
way it would have run live, with no look-ahead.

Why this exists: backtester/engine.py computes every strategy on the WHOLE day, ranks stocks on the
whole day's votes and books entries at the strategy level. Replaying live's logic causally showed that
~all of that engine's LONG profit came from those two pieces of hindsight (notebooks/05).

How it moves (per trading day, strictly in time order):
  1. before 09:15   watchlist from history only (watchlist.pre_filter.PreMarketFilter)
  2. every bar      the next 5-min bar of every watchlist stock (and NIFTY) is released from the parquet
                    file; strategies only ever see the bars released so far
  3. at bar close   if no LONG taken yet today: every strategy is recomputed on the released bars, stocks
                    are ranked on the votes cast so far, and the candidates are walked through live's
                    gates in live's order (live/live_engine._find_live_candidate). First to pass = TAKE.
  4. after entry    the position is managed bar by bar on the bars that follow (stop checked before target
                    inside a bar, gaps fill at the open, trailing lock updated after each completed bar)
Nothing is computed on bars that have not been released. Each decision records the last bar it used;
verify_no_lookahead() re-runs days with every later bar deleted and checks the decision is identical.

Differences from live, all deliberate and configurable (Config):
  * entry at the close of the bar that confirmed the signal (live needs ~3 min to scan)
  * drift gate off by default (live skips when price is >=0.30% past the strategy level)
  * stop: 1% (cap on the strategy stop by default, as live), fills assumed at the chosen price
  * bearish-only strategies are not computed — they can never cast a LONG vote
  * strategies get the last 70 trading days of history (longest lookback is 60 daily bars)
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import (
    STOCKS_DIR, INDEX_DIR, CHECKPOINT_DIR,
    AGREEMENT_MIN_LIFETIME_WR_LONG, MIN_RISK_REWARD, SIGNAL_EXPIRY_MIN,
    MAX_STOP_DISTANCE_PCT, MIN_TARGET_DISTANCE_PCT,
    MIN_STOP_ATR_RATIO, MIN_STOP_ATR_RATIO_OPEN, STOP_VIABILITY_OPEN_UNTIL,
    BROKERAGE_PER_LEG, STT_RATE_SELL, EXCHANGE_RATE, SEBI_RATE, GST_RATE, STAMP_RATE_BUY,
)
from strategies import ALL_STRATEGIES
from strategies.base import Signal
from backtester import engine as legacy
from backtester.composite_scorer import long_composite_score, count_agreeing_filtered
from backtester.quality_filter import passes_all_filters
from weights.regime import get_regime_modifiers, get_direction_bias
from watchlist.pre_filter import PreMarketFilter
from data_pipeline.bars import normalize_bars

ENGINE_VERSION = "1"      # bump when decision/exit logic changes — invalidates cached day results
HIST_DAYS = 70
LONG_STRATEGIES = [s for s in ALL_STRATEGIES if s.category != "bearish"]
_NO = {s.name: Signal(strategy=s.name, direction=0) for s in ALL_STRATEGIES}


@dataclass(frozen=True)
class Config:
    weights: str = "wf5"                  # "wf5" (what live loads) | "uniform" (every strategy 1.0)
    entry: str = "bar_close"              # enter at the close of the bar that confirmed the signal
    drift_gate_pct: float | None = None   # None = off; 0.30 = live's "don't chase" gate
    viability_gate: bool = True           # live's stop-inside-noise gate
    stop_pct: float = 1.0
    stop_mode: str = "cap"                # "cap": strategy stop, but never farther than stop_pct
                                          # "fixed": always exactly stop_pct below entry
    target: str = "strategy"              # "strategy" | "none"
    trail: bool = True                    # live's profit-lock: +trail_trigger% -> trail trail_pct% below best
    trail_trigger_pct: float = 1.0
    trail_pct: float = 0.5
    ride_past_target: bool = True         # once locked, drop the fixed target (live since 07-29)
    first_scan: str = "09:20"
    last_scan: str = "13:55"              # live: no new entries from 14:00
    squareoff_bar: str = "14:45"          # exit at this bar's close = 2:50 PM
    notional: float = 200_000
    slippage_pct: float = 0.0             # per side; 0 = filled at the chosen price (liquid stocks)
    top_n: int = 50

    def key(self) -> str:
        blob = json.dumps({**asdict(self), "_engine": ENGINE_VERSION}, sort_keys=True)
        return hashlib.md5(blob.encode()).hexdigest()[:10]


def _m(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":")[:2])
    return h * 60 + m


def _hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def costs(buy_value: float, sell_value: float, slippage_pct: float) -> float:
    """backtester/cost_model.total_cost with the slippage assumption made explicit."""
    brokerage = BROKERAGE_PER_LEG * 2
    exchange = (buy_value + sell_value) * EXCHANGE_RATE
    return (brokerage + sell_value * STT_RATE_SELL + exchange + (buy_value + sell_value) * SEBI_RATE
            + (brokerage + exchange) * GST_RATE + buy_value * STAMP_RATE_BUY
            + (buy_value + sell_value) * slippage_pct / 100)


def load_weights(kind: str) -> dict:
    if kind == "uniform":
        return {s.name: {"long": 1.0, "short": 1.0} for s in ALL_STRATEGIES}
    return legacy._load_weights(CHECKPOINT_DIR / "wf5_weights.json")


# ─────────────────────────────────────────────────────────────────────────────
# data: whole parquet files are read, but the engine only ever hands out bars in time order
# ─────────────────────────────────────────────────────────────────────────────

class Store:
    """All bars a worker needs for a contiguous block of days (canonical format, day ordinal index)."""

    def __init__(self, days: list[date], symbols: list[str]):
        start = days[0] - timedelta(days=int(HIST_DAYS * 1.6) + 10)
        self.data = {s: d for s in symbols if len(d := self._load(STOCKS_DIR, s, start, days[-1]))}
        self.nifty = self._load(INDEX_DIR, "NIFTY50", start, days[-1])

    @staticmethod
    def _load(base: Path, name: str, start: date, end: date) -> pd.DataFrame:
        # normalise EACH file before joining: years are stored in different tz formats
        parts = [normalize_bars(pd.read_parquet(base / str(y) / f"{name}.parquet"))
                 for y in range(start.year, end.year + 1) if (base / str(y) / f"{name}.parquet").exists()]
        if not parts:
            return pd.DataFrame()
        d = normalize_bars(pd.concat(parts, ignore_index=True))[["datetime", "open", "high", "low", "close", "volume"]]
        d["_d"] = (d.datetime.values.astype("datetime64[D]").astype("int64") + 719163).astype("int32")
        return d[(d._d >= start.toordinal()) & (d._d <= end.toordinal())].reset_index(drop=True)

    @staticmethod
    def split(df: pd.DataFrame, d: date) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(today's bars — to be RELEASED one at a time, history strictly before today)."""
        if df is None or df.empty:
            return pd.DataFrame(), pd.DataFrame()
        o = d.toordinal()
        today = df[df._d == o].drop(columns="_d").reset_index(drop=True)
        hist = df[df._d < o]
        days = np.unique(hist._d.values)
        if len(days) > HIST_DAYS:
            hist = hist[hist._d >= days[-HIST_DAYS]]
        return today, hist.drop(columns="_d").reset_index(drop=True)


def trading_days(start: date, end: date) -> list[date]:
    n = Store._load(INDEX_DIR, "NIFTY50", start, end)
    return sorted(pd.to_datetime(n.datetime).dt.date.unique())


def universe() -> list[str]:
    return sorted(p.stem for p in (STOCKS_DIR / "2026").glob("*.parquet"))


def _turnover_cr(hist: pd.DataFrame) -> float:
    if hist.empty:
        return 0.0
    recent = hist.tail(20 * 75)
    by_day = (recent.close * recent.volume).groupby(recent.datetime.dt.date).sum() / 1e7
    return float(by_day.median()) if len(by_day) else 0.0


def _atr_pct(hist: pd.DataFrame, period: int = 14) -> float | None:
    if hist.empty:
        return None
    daily = hist.groupby(hist.datetime.dt.date).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    if len(daily) < period + 1:
        return None
    pc = daily.close.shift(1)
    tr = pd.concat([daily.high - daily.low, (daily.high - pc).abs(), (daily.low - pc).abs()], axis=1).max(axis=1)
    ref = float(daily.close.iloc[-1])
    return float(tr.tail(period).mean() / ref * 100) if ref > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
# one trading day
# ─────────────────────────────────────────────────────────────────────────────

def simulate_day(store: Store, d: date, cfg: Config, weights: dict, all_symbols: list[str],
                 cutoff_bar: str | None = None) -> dict:
    """Run one day left to right. `cutoff_bar` (used only by verify_no_lookahead) deletes every bar
    after that label before the day starts — the decision must not change."""
    # 1. pre-market: watchlist from history only
    hist_all = {}
    for s in all_symbols:
        _, h = store.split(store.data.get(s), d)
        if len(h):
            hist_all[s] = h
    watchlist = [e["symbol"] for e in PreMarketFilter().build(d, hist_all)]

    today_n, nhist = store.split(store.nifty, d)
    feeds = {}
    for s in watchlist:
        today, hist = store.split(store.data.get(s), d)
        if today.empty or hist.empty:
            continue
        feeds[s] = dict(bars=today, hist=hist, prev=legacy._get_prev_day_ohlc(hist, d),
                        turnover=_turnover_cr(hist), atr=_atr_pct(hist),
                        mins=(today.datetime.dt.hour * 60 + today.datetime.dt.minute).values)
    nmins = (today_n.datetime.dt.hour * 60 + today_n.datetime.dt.minute).values if len(today_n) else np.array([])
    cut = _m(cutoff_bar) if cutoff_bar else None
    if cut is not None:
        for f in feeds.values():
            keep = f["mins"] <= cut
            f["bars"], f["mins"] = f["bars"][keep].reset_index(drop=True), f["mins"][keep]
        keepn = nmins <= cut
        today_n, nmins = today_n[keepn].reset_index(drop=True), nmins[keepn]

    regime_mods = get_regime_modifiers(weights, vix=15.0)
    nifty_pct = 0.0
    long_bias = 1.0
    released_n = today_n.iloc[:0]

    result = {"date": str(d), "watchlist": len(watchlist), "scans": [], "trade": None}
    taken = None
    first, last = _m(cfg.first_scan), _m(cfg.last_scan)

    # 2. walk the session one 5-min bar at a time
    for bar_min in range(9 * 60 + 15, 15 * 60 + 30, 5):
        close_time = bar_min + 5                                   # when this bar is complete
        released_n = today_n[nmins <= bar_min] if len(today_n) else released_n
        if len(released_n) == 1 and len(nhist):
            pc = float(nhist.close.iloc[-1])
            nifty_pct = round((float(released_n.open.iloc[0]) - pc) / pc * 100, 3) if pc > 0 else 0.0
            long_bias, _ = get_direction_bias(15.0, nifty_pct)

        if taken is None and first <= close_time <= last:
            taken, scan_log = _scan(feeds, released_n, bar_min, close_time, d, cfg, weights, regime_mods,
                                    long_bias, nifty_pct)
            result["scans"].append(scan_log)
            if taken is not None:
                taken["nifty_gap_pct"] = nifty_pct
        elif taken is not None and "exit" not in taken:
            _manage(taken, feeds[taken["symbol"]], bar_min, cfg)
        if taken is not None and "exit" not in taken and bar_min >= _m(cfg.squareoff_bar):
            f = feeds[taken["symbol"]]
            upto = f["bars"][f["mins"] <= bar_min]
            _close(taken, float(upto.close.iloc[-1]), _hm(close_time), "TIME_EXIT", cfg)
    if taken is not None and "exit" not in taken:                   # no bars left (cutoff runs only)
        f = feeds[taken["symbol"]]
        _close(taken, float(f["bars"].close.iloc[-1]), _hm(int(f["mins"][-1]) + 5), "TIME_EXIT", cfg)
    result["trade"] = taken
    return result


def _scan(feeds, released_n, bar_min, close_time, d, cfg, weights, regime_mods, long_bias, nifty_pct):
    scored, sigs_of = [], {}
    for s, f in feeds.items():
        n = int((f["mins"] <= bar_min).sum())                     # bars released so far
        if n == 0:
            continue
        today_t = f["bars"].iloc[:n]
        sigs = {}
        for st in LONG_STRATEGIES:
            try:
                sigs[st.name] = st.generate_signal(today_t, f["hist"], f["prev"], released_n, d)
            except Exception:
                sigs[st.name] = _NO[st.name]
        raw = long_composite_score(sigs, weights, regime_mods)
        sigs_of[s] = (sigs, today_t)
        scored.append((s, raw, raw * long_bias))
    scored.sort(key=lambda x: x[2], reverse=True)

    walked = []
    for rank, (s, raw, adj) in enumerate(scored[:cfg.top_n], 1):
        if raw <= 0:
            break
        sigs, today_t = sigs_of[s]
        f = feeds[s]
        best = legacy._best_signal(sigs, direction=+1)
        if best is None:
            continue
        best = dataclasses.replace(best)
        level, stop0, target0 = float(best.entry), float(best.stop), float(best.target)
        px = float(today_t.close.iloc[-1])                       # entry = close of the bar that just closed
        agreeing = count_agreeing_filtered(sigs, +1, legacy._LIFETIME_WR, AGREEMENT_MIN_LIFETIME_WR_LONG)
        pred = legacy._predicted_win_pct(sigs, weights, legacy._LIFETIME_WR, direction=+1)
        age = close_time - _m(best.signal_time) if best.signal_time else None
        stop_d = abs(level - stop0) / level * 100
        tgt_d = abs(target0 - level) / level * 100
        rec = dict(rank=rank, symbol=s, score=round(raw, 2), agreeing=agreeing, pred=pred, driver=best.strategy,
                   signal_time=best.signal_time, reason=best.reason, level=round(level, 2), stop0=round(stop0, 2),
                   target0=round(target0, 2), price=round(px, 2), drift_pct=round((px - level) / level * 100, 3))
        ok, why = passes_all_filters(signal=best, today_5min=today_t, daily_turnover_crore=f["turnover"],
                                     strategies_agreeing=agreeing, composite_score=raw,
                                     predicted_win_pct=pred, nifty_pct_change=nifty_pct)
        if age is not None and age > SIGNAL_EXPIRY_MIN:
            gate = f"SKIP stale signal ({age} min old)"
        elif stop_d > MAX_STOP_DISTANCE_PCT or tgt_d < MIN_TARGET_DISTANCE_PCT:
            gate = f"SKIP geometry (stop {stop_d:.2f}%, target {tgt_d:.2f}%)"
        elif not ok:
            gate = f"FAIL {why}"
        elif px <= stop0 or px >= target0:
            gate = "SKIP price already past stop/target"
        elif cfg.drift_gate_pct is not None and rec["drift_pct"] >= cfg.drift_gate_pct:
            gate = f"SKIP drift {rec['drift_pct']:+.2f}% >= {cfg.drift_gate_pct}%"
        elif (target0 - px) / (px - stop0) < MIN_RISK_REWARD:
            gate = f"SKIP RR {(target0 - px) / (px - stop0):.2f} < {MIN_RISK_REWARD} at entry price"
        else:
            gate = "TAKE"
            if cfg.viability_gate and f["atr"]:
                ratio = ((px - stop0) / px * 100) / f["atr"]
                floor = MIN_STOP_ATR_RATIO_OPEN if close_time < _m(STOP_VIABILITY_OPEN_UNTIL.strftime("%H:%M")) else MIN_STOP_ATR_RATIO
                if ratio < floor:
                    gate = f"SKIP viability (stop {ratio:.2f}x ATR < {floor})"
        rec["gate"] = gate
        walked.append(rec)
        if gate == "TAKE":
            stop = px * (1 - cfg.stop_pct / 100) if cfg.stop_mode == "fixed" else max(stop0, px * (1 - cfg.stop_pct / 100))
            fired = sorted(k for k, v in sigs.items() if v.direction == 1)
            trade = dict(rec, date=str(d), decision_bar=_hm(bar_min), entry_time=_hm(close_time), entry=round(px, 2),
                         stop=round(stop, 2), target=(round(target0, 2) if cfg.target == "strategy" else None),
                         strategies_fired=fired, atr=f["atr"], turnover=f["turnover"],
                         entry_bar=_hm(bar_min), peak=px, trough=px, locked=False, cur_stop=round(stop, 2),
                         stop_path=[(_hm(close_time), round(stop, 2))], skipped_before=[w for w in walked[:-1]])
            return trade, {"scan": _hm(close_time), "candidates": walked[:10], "taken": s}
    return None, {"scan": _hm(close_time), "candidates": walked[:10], "taken": None}


def _manage(t: dict, f: dict, bar_min: int, cfg: Config) -> None:
    """Apply one newly released bar to the open position."""
    i = np.flatnonzero(f["mins"] == bar_min)
    if not len(i):
        return
    b = f["bars"].iloc[int(i[0])]
    close_time = _hm(bar_min + 5)
    hit_s = b.low <= t["cur_stop"]
    tgt_on = t["target"] is not None and not (cfg.ride_past_target and t["locked"])
    hit_t = tgt_on and b.high >= t["target"]
    if hit_s:                                                       # stop first when a bar touches both
        _close(t, min(t["cur_stop"], float(b.open)), close_time, "PROFIT_LOCK_STOP" if t["locked"] else "STOP_HIT", cfg)
        return
    if hit_t:
        _close(t, max(t["target"], float(b.open)), close_time, "TARGET_HIT", cfg)   # gap above target fills at the open
        return
    t["peak"], t["trough"] = max(t["peak"], float(b.high)), min(t["trough"], float(b.low))
    if cfg.trail and (t["peak"] - t["entry"]) / t["entry"] * 100 >= cfg.trail_trigger_pct:
        t["locked"] = True
        new = round(t["peak"] * (1 - cfg.trail_pct / 100), 2)
        if new > t["cur_stop"]:
            t["cur_stop"] = new
            t["stop_path"].append((close_time, new))


def _close(t: dict, px: float, when: str, reason: str, cfg: Config) -> None:
    q = int(cfg.notional // t["entry"])
    buy, sell = t["entry"] * q, px * q
    t.update(exit=round(px, 2), exit_time=when, exit_reason=reason, qty=q,
             gross_rs=round(sell - buy, 2), pnl_rs=round(sell - buy - costs(buy, sell, cfg.slippage_pct), 2),
             ret_pct=round((px - t["entry"]) / t["entry"] * 100, 3),
             mfe_pct=round((t["peak"] - t["entry"]) / t["entry"] * 100, 3),
             mae_pct=round((min(t["trough"], px) - t["entry"]) / t["entry"] * 100, 3))


# ─────────────────────────────────────────────────────────────────────────────
# running a period (parallel over blocks of days, cached per day)
# ─────────────────────────────────────────────────────────────────────────────

CACHE_ROOT = Path(__file__).resolve().parent.parent / "reports" / "causal"


def _block(args) -> list[dict]:
    days, cfg_dict, out_dir = args
    import warnings
    warnings.filterwarnings("ignore")
    cfg = Config(**cfg_dict)
    weights = load_weights(cfg.weights)
    syms = universe()
    store = Store(days, syms)
    out = []
    for d in days:
        f = Path(out_dir) / f"{d}.json"
        if f.exists():
            out.append(json.loads(f.read_text()))
            continue
        r = simulate_day(store, d, cfg, weights, syms)
        f.write_text(json.dumps(r, default=str))
        out.append(r)
    return out


def run_period(start: date, end: date, cfg: Config = Config(), workers: int = 8, block: int = 5,
               progress: bool = True) -> list[dict]:
    """Simulate every trading day in [start, end]. Results are cached per day under
    reports/causal/<config key>/ — re-running with the same Config only computes missing days."""
    from multiprocessing import get_context
    out_dir = CACHE_ROOT / cfg.key()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2))
    days = trading_days(start, end)
    todo = [d for d in days if not (out_dir / f"{d}.json").exists()]
    blocks = [todo[i:i + block] for i in range(0, len(todo), block)]
    if blocks:
        if progress:
            print(f"{len(days)} trading days, {len(todo)} to simulate in {len(blocks)} blocks on {workers} workers "
                  f"(cache: {out_dir})", flush=True)
        with get_context("spawn").Pool(workers, maxtasksperchild=1) as pool:
            for i, _ in enumerate(pool.imap_unordered(_block, [(b, asdict(cfg), str(out_dir)) for b in blocks]), 1):
                if progress:
                    print(f"  block {i}/{len(blocks)} done", flush=True)
    return [json.loads((out_dir / f"{d}.json").read_text()) for d in days]


def trades_frame(results: list[dict]) -> pd.DataFrame:
    rows = [r["trade"] for r in results if r.get("trade")]
    return pd.DataFrame(rows)


def _verify_one(args) -> dict:
    day, t, cfg_dict = args
    import warnings
    warnings.filterwarnings("ignore")
    cfg = Config(**cfg_dict)
    d = date.fromisoformat(day)
    syms = universe()
    again = simulate_day(Store([d], syms), d, cfg, load_weights(cfg.weights), syms, cutoff_bar=t["decision_bar"])["trade"]
    return dict(date=day, symbol=t["symbol"], entry_time=t["entry_time"], entry=t["entry"],
                rerun_symbol=again and again["symbol"], rerun_entry_time=again and again["entry_time"],
                rerun_entry=again and again["entry"],
                identical=bool(again) and again["symbol"] == t["symbol"]
                and again["entry_time"] == t["entry_time"] and abs(again["entry"] - t["entry"]) < 1e-6)


def verify_no_lookahead(results: list[dict], cfg: Config = Config(), sample: int = 15, seed: int = 0,
                        workers: int = 8) -> pd.DataFrame:
    """For a sample of traded days: re-run the day with EVERY bar after the decision bar deleted.
    If the engine used any future bar, the decision (stock, entry time, entry price) would change."""
    import random
    from multiprocessing import get_context
    traded = [r for r in results if r.get("trade")]
    random.seed(seed)
    pick = random.sample(traded, min(sample, len(traded)))
    jobs = [(r["date"], {k: r["trade"][k] for k in ("symbol", "entry_time", "entry", "decision_bar")}, asdict(cfg))
            for r in pick]
    with get_context("spawn").Pool(min(workers, len(jobs)) or 1) as pool:
        rows = pool.map(_verify_one, jobs)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

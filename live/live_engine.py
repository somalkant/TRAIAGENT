"""
Live scan engine — same decision logic as backtester/engine.py _process_day()
but fed from LiveDataManager instead of preloaded parquet files.

Phase 2B: finds best LONG and best SHORT candidate, applies direction bias,
returns the winner. Imports the same private functions from engine.py so
the live system stays byte-for-byte identical to the tested backtester.

scan_once() returns the best recommendation dict (LONG or SHORT), or None.
"""

import logging
from datetime import date, datetime
import pandas as pd
import pytz

_IST = pytz.timezone("Asia/Kolkata")

from backtester.engine import (
    _best_signal,
    _conviction_multiplier,
    _predicted_win_pct,
    _strategies_fired,
    _LIFETIME_WR,
    _get_week52_low,
    _recent_move,
)
from backtester.composite_scorer import (
    long_composite_score, short_composite_score,
    count_agreeing_filtered,
)
from backtester.quality_filter import passes_all_filters
from backtester.position_sizer import position_size
from config.settings import (
    AGREEMENT_MIN_LIFETIME_WR_LONG, AGREEMENT_MIN_LIFETIME_WR_SHORT, SHORT_ENABLED,
    MIN_RISK_REWARD, ENTRY_DRIFT_GATE_PCT, SIGNAL_EXPIRY_MIN,
    MAX_STOP_DISTANCE_PCT, MIN_TARGET_DISTANCE_PCT,
    LIVE_SHORT_SIZE_MULT, OVERLAP_TIGHT_THRESHOLD,
    MAX_POSITION_SIZE, ATR_RISK_BUDGET_RS, ATR_PERIOD_DAYS,
    STOP_VIABILITY_ENABLED, MIN_STOP_ATR_RATIO, MIN_STOP_ATR_RATIO_OPEN,
    STOP_VIABILITY_OPEN_UNTIL,
)
from strategies import ALL_STRATEGIES
from weights.regime import get_regime_modifiers, get_direction_bias
from watchlist.pre_filter import PreMarketFilter
from live.data_manager import LiveDataManager

log = logging.getLogger(__name__)

_TOP_N = 50


def build_live_watchlist(data_manager: LiveDataManager, trade_date: date) -> set[str]:
    """
    Run pre-market filter once before 9:15 AM.

    Call this once per day (e.g. at 9:00 AM) before the first scan_once() call.
    Returns a set of symbols (100 bullish + 100 bearish candidates) for the
    intraday scan. Passing this set to scan_once() avoids scanning all 300+
    stocks on every 5-min candle — no intraday latency added.
    """
    all_data: dict = {}
    for symbol in data_manager.symbols:
        hist = data_manager.get_history(symbol)
        if hist is not None and not hist.empty:
            all_data[symbol] = hist

    pf        = PreMarketFilter()
    watchlist = pf.build(trade_date, all_data)
    symbols   = {e["symbol"] for e in watchlist}
    log.info(f"Live watchlist built: {len(symbols)} symbols for {trade_date}")
    return symbols


def scan_once(
    data_manager: LiveDataManager,
    weights: dict,
    trade_date: date,
    watchlist: set[str] | None = None,
    want_long: bool = True,
    want_short: bool = True,
) -> list[dict]:
    """
    Run one full scan across watchlist symbols using current candle state.

    watchlist: set of symbols from build_live_watchlist() — call that once
               before 9:15 AM and pass the result on every subsequent call.
               If None, falls back to scanning all data_manager.symbols.

    want_long / want_short: skip finding a candidate in that direction when the
               slot is already filled (position already open for that direction).

    Returns a list of 0-2 recommendation dicts — at most one LONG, one SHORT.
    Call this every time a 5-min bar closes.
    """
    if not want_long and not want_short:
        return []
    nifty_today  = data_manager.get_nifty_today()
    vix          = _estimate_vix()
    nifty_pct    = _estimate_nifty_pct(data_manager)
    regime_mods  = get_regime_modifiers(weights, vix=vix)
    long_bias, short_bias = get_direction_bias(vix, nifty_pct)

    stock_signals:      dict[str, dict]   = {}
    stock_long_scores:  dict[str, tuple]  = {}   # {symbol: (raw, adj)}
    stock_short_scores: dict[str, tuple]  = {}

    symbols_to_scan = watchlist if watchlist is not None else set(data_manager.symbols)
    for symbol in symbols_to_scan:
        today_5min   = data_manager.get_today(symbol)
        history_5min = data_manager.get_history(symbol)
        prev_day     = data_manager.get_prev_day(symbol)

        if today_5min.empty:
            log.debug(f"  {symbol}: 0 bars today — skipping")
            continue

        signals = {}
        for strategy in ALL_STRATEGIES:
            try:
                sig = strategy.generate_signal(
                    today_5min=today_5min,
                    history_5min=history_5min,
                    prev_day=prev_day,
                    nifty_today=nifty_today,
                    trade_date=trade_date,
                )
                signals[strategy.name] = sig
            except Exception as e:
                from strategies.base import Signal
                signals[strategy.name] = Signal(strategy=strategy.name, direction=0)
                log.debug(f"  {symbol}/{strategy.name}: signal error — {e}")

        stock_signals[symbol] = signals
        ls_raw = long_composite_score(signals, weights, regime_mods)
        ss_raw = short_composite_score(signals, weights, regime_mods)
        stock_long_scores[symbol]  = (ls_raw, ls_raw * long_bias)
        stock_short_scores[symbol] = (ss_raw, ss_raw * short_bias)

    zero_bar_stocks = [s for s in symbols_to_scan if data_manager.get_today(s).empty]
    if zero_bar_stocks:
        log.info(f"  !! {len(zero_bar_stocks)} watchlist stocks have 0 bars: "
                 f"{', '.join(zero_bar_stocks[:10])}")

    if not stock_signals:
        return []

    daily_turnover = _estimate_turnover(data_manager, symbols_to_scan)
    results: list[dict] = []

    # ── Find best LONG candidate ─────────────────────────────────────────────
    if want_long:
        sorted_longs = sorted(stock_long_scores.items(), key=lambda x: x[1][1], reverse=True)
        _log_top_candidates(sorted_longs, stock_signals, data_manager,
                            daily_turnover, weights, direction=+1, nifty_pct=nifty_pct)
        best_long = _find_live_candidate(
            direction=+1,
            sorted_stocks=sorted_longs,
            stock_signals=stock_signals,
            data_manager=data_manager,
            daily_turnover=daily_turnover,
            weights=weights,
            nifty_pct=nifty_pct,
            vix=vix,
        )
        if best_long:
            results.append(best_long)

    # ── Find best SHORT candidate ────────────────────────────────────────────
    if want_short and SHORT_ENABLED:
        sorted_shorts = sorted(stock_short_scores.items(), key=lambda x: x[1][1], reverse=True)
        _log_top_candidates(sorted_shorts, stock_signals, data_manager,
                            daily_turnover, weights, direction=-1, nifty_pct=nifty_pct)
        best_short = _find_live_candidate(
            direction=-1,
            sorted_stocks=sorted_shorts,
            stock_signals=stock_signals,
            data_manager=data_manager,
            daily_turnover=daily_turnover,
            weights=weights,
            nifty_pct=nifty_pct,
            vix=vix,
        )
        if best_short:
            results.append(best_short)

    return results


def _find_live_candidate(
    direction: int,
    sorted_stocks: list,
    stock_signals: dict,
    data_manager: LiveDataManager,
    daily_turnover: dict,
    weights: dict,
    nifty_pct: float,
    vix: float,
) -> dict | None:
    for symbol, (raw_score, adj_score) in sorted_stocks[:_TOP_N]:
        if raw_score <= 0:
            break

        signals  = stock_signals.get(symbol)
        if not signals:
            continue
        today_5m = data_manager.get_today(symbol)

        best_sig = _best_signal(signals, direction=direction)
        if best_sig is None:
            continue

        # ── Signal staleness — a driver signal can be a re-fired pivot level from
        #    earlier in the day (signal_time doesn't advance). Discard if too old;
        #    this is what let the 146-min-lag fill happen in the live/backtest review.
        now_ist = datetime.now(_IST)
        sig_age_min = _signal_age_minutes(best_sig.signal_time, now_ist)
        if sig_age_min is not None and sig_age_min > SIGNAL_EXPIRY_MIN:
            log.debug(f"  {symbol}: signal stale ({sig_age_min:.0f} min old > {SIGNAL_EXPIRY_MIN}) — skip")
            continue

        # ── Risk-geometry rejection gates (reject only — never move stop/target) ──
        stop_dist_pct   = abs(best_sig.entry - best_sig.stop)   / best_sig.entry * 100 if best_sig.entry else 0
        target_dist_pct = abs(best_sig.target - best_sig.entry) / best_sig.entry * 100 if best_sig.entry else 0
        if stop_dist_pct > MAX_STOP_DISTANCE_PCT:
            log.debug(f"  {symbol}: stop distance {stop_dist_pct:.2f}% > {MAX_STOP_DISTANCE_PCT}% — skip")
            continue
        if target_dist_pct < MIN_TARGET_DISTANCE_PCT:
            log.debug(f"  {symbol}: target distance {target_dist_pct:.2f}% < {MIN_TARGET_DISTANCE_PCT}% — skip")
            continue

        wr_gate      = AGREEMENT_MIN_LIFETIME_WR_LONG if direction == 1 else AGREEMENT_MIN_LIFETIME_WR_SHORT
        agreeing     = count_agreeing_filtered(signals, direction, _LIFETIME_WR, wr_gate)
        turnover     = daily_turnover.get(symbol, 0)
        pred_win_pct = _predicted_win_pct(signals, weights, _LIFETIME_WR, direction=direction)

        today        = date.today()
        week52_low   = _get_week52_low(data_manager.get_history(symbol), today) if direction == -1 else 0.0
        recent_3d_mv = _recent_move(data_manager.get_history(symbol), today, days=3) if direction == -1 else 0.0

        passes, reason = passes_all_filters(
            signal               = best_sig,
            today_5min           = today_5m,
            daily_turnover_crore = turnover,
            strategies_agreeing  = agreeing,
            composite_score      = raw_score,
            predicted_win_pct    = pred_win_pct,
            nifty_pct_change     = nifty_pct,
            week52_low           = week52_low,
            recent_3day_move     = recent_3d_mv,
        )

        if passes:
            live_price     = data_manager.get_last_price(symbol)
            strategy_entry = best_sig.entry
            drift_pct      = 0.0

            if live_price and live_price > 0:
                # ── Guard: live price already through stop or past target — signal is dead ──
                if direction == +1 and (live_price <= best_sig.stop or live_price >= best_sig.target):
                    log.debug(f"  {symbol}: live price {live_price:.2f} already past stop/target — skip")
                    continue
                if direction == -1 and (live_price >= best_sig.stop or live_price <= best_sig.target):
                    log.debug(f"  {symbol}: live price {live_price:.2f} already past stop/target — skip")
                    continue

                # ── Entry fidelity gate — do NOT chase price and do NOT re-anchor
                #    stop/target to the live price. Fill at the live price only if it
                #    hasn't moved unfavorably beyond ENTRY_DRIFT_GATE_PCT from the
                #    researched entry; otherwise skip the trade outright (no resting
                #    order, no waiting for a retracement).
                if direction == +1:
                    drift_pct = (live_price - strategy_entry) / strategy_entry * 100   # +ve = paying more (bad)
                else:
                    drift_pct = (strategy_entry - live_price) / strategy_entry * 100   # +ve = selling for less (bad)

                if drift_pct >= ENTRY_DRIFT_GATE_PCT:
                    log.info(
                        f"  {symbol} [{'LONG' if direction==+1 else 'SHORT'}]: SKIPPED — price moved "
                        f"{drift_pct:+.2f}% unfavorable vs researched entry {strategy_entry:.2f} "
                        f"(live {live_price:.2f}), gate={ENTRY_DRIFT_GATE_PCT}% — not chasing"
                    )
                    continue

                # Fill at the actual live price. Stop/target stay at the researched levels.
                best_sig.entry = round(live_price, 2)
                if direction == +1:
                    new_rr = (best_sig.target - best_sig.entry) / (best_sig.entry - best_sig.stop)
                else:
                    new_rr = (best_sig.entry - best_sig.target) / (best_sig.stop - best_sig.entry)
                best_sig.rr = round(new_rr, 2)

                if best_sig.rr < MIN_RISK_REWARD:
                    log.debug(f"  {symbol}: RR degraded to {best_sig.rr:.2f} after fill-price recheck — skip")
                    continue

            # ── Candle-overlap confidence tier (compression before the move) ──────
            overlap_ratio, overlap_tier = _overlap_confidence(today_5m)

            conv_mult, conv_tier = _conviction_multiplier(best_sig.strategy, direction)
            if overlap_tier == "LOOSE" and conv_tier in ("HIGH", "MEDIUM"):
                # Compression signal doesn't support elevated conviction — cap sizing.
                conv_tier = "STANDARD"
                conv_mult = 1.0

            # Short-side multiplier scales BOTH the risk budget and the notional
            # cap (scaling risk alone does nothing when the cap binds — seen live
            # on POLICYBZR 2026-07-17). At 1.0 (paper trading) this is a no-op;
            # set LIVE_SHORT_SIZE_MULT=0.5 for real-money pilot sizing.
            short_haircut = False
            if direction == -1 and LIVE_SHORT_SIZE_MULT != 1.0:
                conv_mult *= LIVE_SHORT_SIZE_MULT
                short_haircut = True

            # ── Volatility-normalized sizing (professional constant-risk) ─────────
            # notional = min(cap, stop_risk/stop%, ATR_budget/ATR%): every position
            # targets the same rupee move on an average day. Strategy stops track
            # real volatility poorly (0.16 correlation measured over the first 42
            # live trades) — the ATR term is what catches a deceptively tight stop
            # on a wild name (2% stop on a 5% ATR stock = noise stop at max size).
            atr = _atr_pct_from_history(data_manager.get_history(symbol))

            # ── Stop-viability gate (reject-only) ─────────────────────────────
            # A stop that is a trivial fraction of ATR sits inside the noise band
            # and has near-zero survival odds regardless of the directional call
            # (HINDALCO 2026-07-23: 0.15% stop on 2.17% ATR = 7% of a daily range,
            # noise-stopped in 75s). Reject — never widen — and let the scan fall
            # through to the next-best candidate. Strictest in the opening window.
            if STOP_VIABILITY_ENABLED and atr and atr > 0:
                stop_pct_now = abs(best_sig.entry - best_sig.stop) / best_sig.entry * 100
                ratio        = stop_pct_now / atr
                in_open      = now_ist.time() < STOP_VIABILITY_OPEN_UNTIL
                floor        = MIN_STOP_ATR_RATIO_OPEN if in_open else MIN_STOP_ATR_RATIO
                if ratio < floor:
                    _dirn = "LONG" if direction == +1 else "SHORT"
                    log.info(
                        f"  SKIP [viability] {symbol} [{_dirn}]: driver={best_sig.strategy} "
                        f"entry={best_sig.entry:.2f} stop={best_sig.stop:.2f} "
                        f"target={best_sig.target:.2f} RR={best_sig.rr:.2f} | "
                        f"stop {stop_pct_now:.2f}% = {ratio:.2f}x ATR({atr:.1f}%) "
                        f"< floor {floor:.2f}x{' [open window]' if in_open else ''} — "
                        f"stop inside noise band, skipping (next candidate gets the slot)"
                    )
                    continue

            notional_cap = MAX_POSITION_SIZE * (LIVE_SHORT_SIZE_MULT if direction == -1 else 1.0)
            rs_value, shares = position_size(
                best_sig.entry, best_sig.stop, conv_mult,
                atr_pct=atr, atr_risk_rs=ATR_RISK_BUDGET_RS, max_notional=notional_cap,
            )
            size_cap_reason = _binding_constraint(
                best_sig.entry, best_sig.stop, conv_mult, atr, notional_cap)
            entry_time = now_ist.strftime("%H:%M")

            dirn_str = "LONG" if direction == +1 else "SHORT"
            log.info(
                f"SIGNAL [{dirn_str}]: {symbol} | driver={best_sig.strategy} | "
                f"signal_time={best_sig.signal_time} entry_time={entry_time} (age={sig_age_min or 0:.0f}m) | "
                f"entry={best_sig.entry:.2f} (drift={drift_pct:+.2f}%) | "
                f"target={best_sig.target:.2f} stop={best_sig.stop:.2f} RR={best_sig.rr:.2f} | "
                f"agreeing={agreeing} score={adj_score:.2f} pred={pred_win_pct:.1f}% | "
                f"overlap={overlap_ratio if overlap_ratio is not None else 'n/a'} [{overlap_tier}] | "
                f"ATR14={f'{atr:.1f}%' if atr else 'n/a'} | "
                f"size=Rs {rs_value:,.0f} ({shares} shares) [{conv_tier}, sized by {size_cap_reason}]"
                + (f" [SHORT {LIVE_SHORT_SIZE_MULT}x risk+cap]" if short_haircut else "")
            )
            sig_dict                   = best_sig.to_dict()
            sig_dict["strategy_entry"] = strategy_entry
            return {
                "symbol":            symbol,
                "score":             round(adj_score, 3),
                "raw_score":         round(raw_score, 3),
                "direction":         dirn_str,
                "signal":            sig_dict,
                "entry_time":        entry_time,
                "entry_drift_pct":   round(drift_pct, 3),
                "signal_age_min":    round(sig_age_min, 1) if sig_age_min is not None else 0.0,
                "overlap_ratio":     overlap_ratio,
                "overlap_tier":      overlap_tier,
                "atr_pct":           round(atr, 2) if atr is not None else None,
                "size_cap_reason":   size_cap_reason,
                "agreeing":          agreeing,
                "position_rs":       rs_value,
                "shares":            shares,
                "predicted_win_pct": pred_win_pct,
                "conviction_tier":   conv_tier,
                "conviction_mult":   conv_mult,
                "strategies_fired":  _strategies_fired(signals, direction),
                "vix":               vix,
            }
        else:
            log.debug(f"  {symbol} [{('LONG' if direction==+1 else 'SHORT')}] filtered: {reason}")

    return None


def _atr_pct_from_history(hist, period: int = ATR_PERIOD_DAYS) -> float | None:
    """
    14-day daily ATR as % of the latest close, from 5-min parquet history
    (which ends yesterday — no look-ahead). None if under period+1 days of data.
    """
    if hist is None or hist.empty:
        return None
    try:
        daily = (hist.groupby(hist["datetime"].dt.date)
                 .agg(high=("high", "max"), low=("low", "min"), close=("close", "last")))
        if len(daily) < period + 1:
            return None
        pc = daily["close"].shift(1)
        tr = pd.concat([daily["high"] - daily["low"],
                        (daily["high"] - pc).abs(),
                        (daily["low"] - pc).abs()], axis=1).max(axis=1)
        ref = float(daily["close"].iloc[-1])
        if ref <= 0:
            return None
        return float(tr.tail(period).mean() / ref * 100)
    except Exception:
        return None


def _binding_constraint(entry: float, stop: float, conv_mult: float,
                        atr: float | None, notional_cap: float) -> str:
    """Which sizing term won: NOTIONAL_CAP, STOP_RISK, or ATR_VOL (for the log/CSV)."""
    from config.settings import MAX_LOSS_PER_TRADE
    stop_pct = abs(entry - stop) / entry if entry else 0
    terms = {"NOTIONAL_CAP": notional_cap}
    if stop_pct > 0:
        terms["STOP_RISK"] = MAX_LOSS_PER_TRADE * conv_mult / stop_pct
    if atr and atr > 0:
        terms["ATR_VOL"] = ATR_RISK_BUDGET_RS / (atr / 100)
    return min(terms, key=terms.get)


def _signal_age_minutes(signal_time: str, now_ist: datetime) -> float | None:
    """Minutes elapsed since the driver's signal_time (today, IST). None if unparseable."""
    if not signal_time:
        return None
    try:
        h, m = map(int, signal_time.split(":"))
        sig_dt = now_ist.replace(hour=h, minute=m, second=0, microsecond=0)
        return max(0.0, (now_ist - sig_dt).total_seconds() / 60.0)
    except Exception:
        return None


def _overlap_confidence(today_5m) -> tuple[float | None, str]:
    """
    Price-compression confidence tier over the last 3 completed 5-min bars.
    overlap_ratio = width(intersection of [low,high] ranges) / width(union).
    High ratio = tight consolidation (compression before a move) = higher confidence.
    Returns (ratio, "TIGHT"|"LOOSE"|"N/A"). N/A when fewer than 3 bars exist yet
    (true for most of the 09:15-09:30 window where this system enters most trades).
    """
    if today_5m is None or len(today_5m) < 3:
        return None, "N/A"
    last3 = today_5m.tail(3)
    inter_low, inter_high = last3["low"].max(), last3["high"].min()
    union_low, union_high = last3["low"].min(), last3["high"].max()
    union_width = union_high - union_low
    if union_width <= 0:
        return None, "N/A"
    ratio = max(0.0, inter_high - inter_low) / union_width
    tier  = "TIGHT" if ratio >= OVERLAP_TIGHT_THRESHOLD else "LOOSE"
    return round(ratio, 3), tier


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_vix() -> float:
    return 15.0


def _estimate_nifty_pct(data_manager: LiveDataManager) -> float:
    """Estimate Nifty's opening change vs prior day close (available at 9:20 AM)."""
    try:
        nifty_today = data_manager.get_nifty_today()
        nifty_hist  = data_manager.get_nifty_history()
        if nifty_today.empty or nifty_hist is None or nifty_hist.empty:
            return 0.0
        prev_close  = float(nifty_hist.iloc[-1]["close"])
        today_open  = float(nifty_today.iloc[0]["open"])
        if prev_close <= 0:
            return 0.0
        return round((today_open - prev_close) / prev_close * 100, 3)
    except Exception:
        return 0.0


def _log_top_candidates(
    sorted_stocks: list,
    stock_signals: dict,
    data_manager: LiveDataManager,
    daily_turnover: dict,
    weights: dict,
    direction: int,
    nifty_pct: float = 0.0,
) -> None:
    dirn_str = "LONG" if direction == +1 else "SHORT"
    shown = 0
    for symbol, score_pair in sorted_stocks[:20]:
        raw_score = score_pair[0]
        if raw_score <= 0 or shown >= 3:
            break
        signals      = stock_signals[symbol]
        today_5m     = data_manager.get_today(symbol)
        wr_gate      = AGREEMENT_MIN_LIFETIME_WR_LONG if direction == 1 else AGREEMENT_MIN_LIFETIME_WR_SHORT
        agreeing     = count_agreeing_filtered(signals, direction, _LIFETIME_WR, wr_gate)
        turnover     = daily_turnover.get(symbol, 0)
        pred_win_pct = _predicted_win_pct(signals, weights, _LIFETIME_WR, direction=direction)
        best_sig     = _best_signal(signals, direction=direction)
        if best_sig is None:
            log.info(f"    [{dirn_str}] {symbol}: score={raw_score:.2f} — no valid signal")
        else:
            today        = date.today()
            week52_low   = _get_week52_low(data_manager.get_history(symbol), today) if direction == -1 else 0.0
            recent_3d_mv = _recent_move(data_manager.get_history(symbol), today, days=3) if direction == -1 else 0.0
            passes, reason = passes_all_filters(
                signal               = best_sig,
                today_5min           = today_5m,
                daily_turnover_crore = turnover,
                strategies_agreeing  = agreeing,
                composite_score      = raw_score,
                predicted_win_pct    = pred_win_pct,
                nifty_pct_change     = nifty_pct,
                week52_low           = week52_low,
                recent_3day_move     = recent_3d_mv,
            )
            n_bars = len(today_5m)
            if passes:
                log.info(f"    [{dirn_str}] {symbol}: score={raw_score:.2f} agreeing={agreeing} "
                         f"bars={n_bars} PASS")
            else:
                log.info(f"    [{dirn_str}] {symbol}: score={raw_score:.2f} agreeing={agreeing} "
                         f"bars={n_bars} FAIL — {reason}")
        shown += 1


def _estimate_turnover(data_manager: LiveDataManager,
                       symbols: set[str] | None = None) -> dict[str, float]:
    result: dict[str, float] = {}
    for symbol in (symbols if symbols is not None else data_manager.symbols):
        hist = data_manager.get_history(symbol)
        if hist is None or hist.empty:
            result[symbol] = 0
            continue
        recent = hist.tail(20 * 75)
        by_day = recent.groupby(recent["datetime"].dt.date).apply(
            lambda x: (x["close"] * x["volume"]).sum() / 1e7
        )
        result[symbol] = float(by_day.median()) if not by_day.empty else 0
    return result

"""
Live Paper Trading Agent — Top-10 correlation-reduced strategy roster.

Replaces the old 38-strategy composite-scored agent (live/agent.py) as the
default daily entry point. Independent of that system: fixed 10-strategy
roster (top10_backtest/strategies.py), own Rs 10L capital per strategy
(Rs 5L long / Rs 5L short, non-compounding), max 1 long + 1 short trade per
strategy per day (up to 20 concurrent open positions), exit rule identical to
the backtest (_simulate_outcome-equivalent target/stop/15:15 time-exit, no
profit-lock) so live results stay comparable to the backtest numbers.

Daily usage (run before 9:15 AM):
    python run_live_top10.py

Reuses, unchanged, from the old live/ package:
  - live/data_manager.py::LiveDataManager  (candle building, history, depth)
  - live/fill_check.py::check_fill/simulate_fill  (order-book fill simulation)
  - live/instrument_map.py::load_instrument_map
  - live/candle_checkpoint.py (via LiveDataManager)
  - live/agent.py's private pre-market helpers (_load_universe_symbols,
    _load_history_for_symbols, _fill_parquet_gaps, _backfill_today_bars,
    _run_eod_download) — pure data-loading mechanics with no dependency on
    the old composite-scoring system.

Crash safety:
  - Open-position state for all 10 strategies is checkpointed to
    checkpoints/top10_live_open_trades.json — restart resumes monitoring.
"""

import argparse
import json
import logging
import threading
import time as time_mod
from datetime import date, datetime, timedelta, time as dtime

import pytz

from config.settings import TOP10_FILL_TOLERANCE_PCT, TOP10_MIN_FILL_RATIO
from live.instrument_map import load_instrument_map, NIFTY50_TOKEN
from live.data_manager import LiveDataManager
from live.fill_check import check_fill, simulate_fill
from live.top10_logger import save_open_trades, load_open_trades, log_closed_trade
from live.top10_risk_guard import check_risk_limits, write_eod_risk_check
from live.agent import (
    _load_universe_symbols, _load_history_for_symbols, _fill_parquet_gaps,
    _backfill_today_bars, _run_eod_download,
)

from top10_backtest.strategies import TOP10_STRATEGIES, TOP10_NAMES
from top10_backtest.universe import long_universe, short_universe
from top10_backtest.capital import size
from top10_backtest.strength import classify_strength

log = logging.getLogger(__name__)

IST         = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
NO_ENTRY    = dtime(14, 0)    # no new positions after 2:00 PM (also enforced inside each strategy)
SQUARE_OFF  = dtime(15, 15)   # force exit at 3:15 PM


# ─────────────────────────────────────────────────────────────────────────────
# Agent state — up to one open LONG + one open SHORT PER STRATEGY
# ─────────────────────────────────────────────────────────────────────────────

class Top10AgentState:
    """
    {strategy_name: {"long": rec|None, "short": rec|None,
                      "long_placed": bool, "short_placed": bool}}
    `long_placed`/`short_placed` stay True even after the position closes, to
    block re-entry for that strategy/side for the rest of the day.
    """

    def __init__(self, strategy_names: list[str]):
        self._state = {
            name: {"long": None, "short": None, "long_placed": False, "short_placed": False}
            for name in strategy_names
        }
        self._lock = threading.Lock()

    def set(self, strategy: str, side: str, rec: dict) -> None:
        key = side.lower()
        with self._lock:
            self._state[strategy][key] = rec
            self._state[strategy][f"{key}_placed"] = True

    def close(self, strategy: str, side: str) -> None:
        key = side.lower()
        with self._lock:
            self._state[strategy][key] = None

    def unplace(self, strategy: str, side: str) -> None:
        """Clear the placed flag after a voided (never-filled) trade, so this
        strategy/side can be scanned again later the same day."""
        key = side.lower()
        with self._lock:
            self._state[strategy][key] = None
            self._state[strategy][f"{key}_placed"] = False

    def get_placed(self, strategy: str, side: str) -> bool:
        key = side.lower()
        with self._lock:
            return self._state[strategy][f"{key}_placed"]

    def any_placed(self) -> bool:
        with self._lock:
            return any(s["long_placed"] or s["short_placed"] for s in self._state.values())

    def any_open(self) -> bool:
        with self._lock:
            return any(s["long"] is not None or s["short"] is not None for s in self._state.values())

    def iter_open(self) -> list[tuple[str, str, dict]]:
        with self._lock:
            out = []
            for name, s in self._state.items():
                if s["long"] is not None:
                    out.append((name, "LONG", s["long"]))
                if s["short"] is not None:
                    out.append((name, "SHORT", s["short"]))
            return out

    def snapshot(self) -> dict:
        with self._lock:
            return {name: dict(s) for name, s in self._state.items()}

    def restore(self, saved: dict) -> None:
        with self._lock:
            for name, s in saved.items():
                if name in self._state:
                    self._state[name] = dict(s)


class SymbolSideRegistry:
    """
    Cross-strategy exclusivity for the whole trading day: once a strategy
    claims (symbol, side), no OTHER strategy may take the same side of that
    symbol today. The opposite side stays open to a different strategy — a
    LONG from one strategy and a SHORT from another on the same stock is a
    genuine, independent bet, not a duplicated one. Exclusivity persists for
    the rest of the day even after the claiming position closes (the point is
    to avoid two pools riding the same bet, not just avoiding literal
    concurrent overlap).
    """

    def __init__(self):
        self._taken: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def is_available(self, symbol: str, side: str, strategy: str) -> bool:
        with self._lock:
            holder = self._taken.get((symbol, side))
            return holder is None or holder == strategy

    def claim(self, symbol: str, side: str, strategy: str) -> None:
        with self._lock:
            self._taken[(symbol, side)] = strategy


def _build_symbol_side_registry(today: date, state: Top10AgentState) -> SymbolSideRegistry:
    """Rebuilds today's claims from the trades CSV (source of truth) plus any
    currently-open positions — makes this restart-safe with no separate
    checkpoint file to keep in sync."""
    import pandas as pd
    from live.top10_logger import TRADES_FILE

    registry = SymbolSideRegistry()
    if TRADES_FILE.exists():
        try:
            df = pd.read_csv(TRADES_FILE)
            today_rows = df[df["date"] == str(today)]
            for _, row in today_rows.iterrows():
                registry.claim(row["symbol"], row["side"], row["strategy"])
        except Exception as e:
            log.warning(f"Could not rebuild symbol/side registry from trades CSV: {e}")

    for strategy_name, side, rec in state.iter_open():
        registry.claim(rec["symbol"], side, strategy_name)

    return registry


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args  = _parse_args()
    today = date.today()

    log.info("=" * 65)
    log.info(f"  Live Paper Trading Agent — Top-10 Strategy Roster — {today}")
    log.info("=" * 65)

    # ── 1. Authenticate ─────────────────────────────────────────────────────
    from brokers import get_broker  # noqa: PLC0415  (lazy — avoids kiteconnect SSL/WS init hang)
    broker = get_broker(args.broker)
    log.info(f"Loading {broker.display_name} API classes...")
    KiteConnect, KiteTicker = broker.get_api_classes()

    api_key, access_token = broker.get_credentials(args)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    log.info(f"{broker.display_name} authenticated successfully")

    # ── 2. Instrument map + gap-fill ─────────────────────────────────────────
    imap = load_instrument_map(kite, args.broker)
    _fill_parquet_gaps(kite, imap, today)

    # ── 3. Risk limits — whole-system halt exits; per-strategy halts noted ──
    halted = check_risk_limits(today, TOP10_NAMES)

    # ── 4. Universe: full history load, then LONG (>=300cr turnover) / SHORT (F&O) split ──
    universe_symbols = _load_universe_symbols()
    log.info(f"Universe: {len(universe_symbols)} stocks — loading parquet history...")
    all_history = _load_history_for_symbols(universe_symbols, today)
    log.info(f"History loaded for {len(all_history)} symbols")

    long_syms  = long_universe(all_history, today)
    short_syms = short_universe(all_history, today)
    active     = sorted(long_syms | short_syms)
    log.info(f"LONG universe (>=300cr turnover): {len(long_syms)} stocks")
    log.info(f"SHORT universe (F&O list): {len(short_syms)} stocks")
    log.info(f"Active scan universe: {len(active)} stocks")

    # ── 5. Data manager — reuse already-loaded history, don't reload from parquet ──
    dm = LiveDataManager(symbols=active, imap=imap)
    for sym in active:
        if sym in all_history:
            dm._history[sym] = all_history[sym]
    dm._load_nifty_history([today.year - 1, today.year], today)
    del all_history

    # ── 5b. Resume today's candle bars + late-start backfill ────────────────
    dm.resume_from_checkpoint(today)
    now_ist = _now_ist()
    if now_ist.time() > dtime(9, 20):
        market_open_dt = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        last_closed_t  = now_ist.replace(
            minute=(now_ist.minute // 5) * 5, second=0, microsecond=0
        ) - timedelta(minutes=5)
        expected_bars = max(0, int((last_closed_t - market_open_dt).total_seconds() / 300) + 1)
        actual_bars = max(
            (len(dm._builders[s].closed_bars) for s in dm.symbols[:5] if dm._builders[s].closed_bars),
            default=0,
        )
        if expected_bars > 0 and actual_bars < expected_bars * 0.8:
            log.info(f"Candle history incomplete: {actual_bars} bars vs {expected_bars} expected "
                     f"— backfilling from {broker.display_name} API")
            _backfill_today_bars(kite, dm, today, broker.display_name)

    # ── 6. Restore crash-recovered open positions ────────────────────────────
    state = Top10AgentState(TOP10_NAMES)
    _, saved_state = load_open_trades()
    if saved_state:
        state.restore(saved_state)
        for name, s in saved_state.items():
            if s.get("long"):
                log.info(f"RECOVERED open LONG  [{name}]: {s['long']['symbol']} — monitoring for exit")
            if s.get("short"):
                log.info(f"RECOVERED open SHORT [{name}]: {s['short']['symbol']} — monitoring for exit")

    symbol_registry = _build_symbol_side_registry(today, state)

    # ── 7. Ticker WebSocket setup ────────────────────────────────────────────
    tokens     = dm.instrument_tokens
    _last_tick = [None]
    _ws_holder = [None]

    log.info(f"Subscribing {len(tokens)} instrument tokens to {broker.display_name} ticker")

    def _make_ticker():
        try:
            new_ws = KiteTicker(api_key, access_token, reconnect=True, reconnect_max_tries=50)
        except TypeError:
            new_ws = KiteTicker(api_key, access_token)

        def on_connect(ws, _response):
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            log.info(f"{broker.display_name} ticker connected and subscribed")

        def on_ticks(_ws, ticks):
            _last_tick[0] = datetime.now()
            for tick in ticks:
                dm.on_tick(tick)
            if state.any_open():
                _check_exit_all(state, dm, today)

        def on_depth(_ws, depth_ticks):
            for dtick in depth_ticks:
                dm.on_depth_update(dtick["instrument_token"], dtick)

        def on_close(_ws, code, reason):
            log.warning(f"Ticker disconnected: {code} {reason}")

        def on_error(_ws, code, reason):
            log.error(f"Ticker error: {code} {reason}")

        new_ws.on_connect = on_connect
        new_ws.on_ticks   = on_ticks
        new_ws.on_close   = on_close
        new_ws.on_error   = on_error
        if hasattr(new_ws, "on_depth"):
            new_ws.on_depth = on_depth
        new_ws.connect(threaded=True)
        return new_ws

    _ws_holder[0] = _make_ticker()

    log.info("Waiting for market open (9:15 AM IST)...")

    # ── 8. Main scheduling loop ──────────────────────────────────────────────
    try:
        _run_market_loop(_ws_holder, _last_tick, _make_ticker, dm, state, halted,
                         long_syms, short_syms, today, symbol_registry)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        if _ws_holder[0]:
            _ws_holder[0].close()
        log.info("Ticker disconnected. Agent stopped.")

    # ── 9. Day summary + EOD risk check ──────────────────────────────────────
    _print_summary(state, today)
    write_eod_risk_check(today, TOP10_NAMES)

    # ── 10. Post-market EOD data download ────────────────────────────────────
    _run_eod_download(kite, imap, today)


# ─────────────────────────────────────────────────────────────────────────────
# Market loop — runs in main thread
# ─────────────────────────────────────────────────────────────────────────────

_TICKER_STALE_SECS = 300

def _run_market_loop(ws_holder: list, last_tick: list, make_ticker,
                     dm: LiveDataManager, state: Top10AgentState,
                     halted: dict, long_syms: set, short_syms: set, today: date,
                     symbol_registry: SymbolSideRegistry) -> None:
    while True:
        now   = _now_ist()
        now_t = now.time()

        if now_t >= SQUARE_OFF:
            _force_time_exit_all(state, dm, today, now_t.strftime("%H:%M"))
            break

        next_bar_dt = _next_bar_close(now)
        sleep_secs  = (next_bar_dt - now).total_seconds() + 0.3
        if sleep_secs > 0:
            time_mod.sleep(sleep_secs)

        now   = _now_ist()
        now_t = now.time()

        if now_t < MARKET_OPEN:
            continue

        # ── Ticker staleness check / reconnect ───────────────────────────────
        if MARKET_OPEN <= now_t < SQUARE_OFF and last_tick[0] is not None:
            age = (datetime.now() - last_tick[0]).total_seconds()
            if age > _TICKER_STALE_SECS:
                log.warning(f"Ticker stale: no ticks for {age:.0f}s — reconnecting...")
                try:
                    ws_holder[0].close()
                except Exception:
                    pass
                time_mod.sleep(2)
                try:
                    ws_holder[0] = make_ticker()
                    last_tick[0] = datetime.now()
                    log.info("Ticker reconnected successfully")
                except Exception as e:
                    log.error(f"Ticker reconnect failed: {e} — will retry next bar")

        # Close the completed 5-min bar
        bar_label = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
        bar_label = bar_label.replace(tzinfo=None)
        if bar_label.time() < MARKET_OPEN:
            continue
        dm.close_bar(bar_label)
        log.debug(f"Bar closed: {bar_label.strftime('%H:%M')}")

        # ── Scan each of the 10 strategies independently ─────────────────────
        if now_t < NO_ENTRY:
            nifty_today = dm.get_nifty_today()
            any_scanned = False
            for strategy in TOP10_STRATEGIES:
                name = strategy.name
                want_long  = (not state.get_placed(name, "LONG")
                              and (name, "LONG") not in halted)
                want_short = (not state.get_placed(name, "SHORT")
                              and (name, "SHORT") not in halted)
                if not want_long and not want_short:
                    continue
                any_scanned = True

                long_candidates, short_candidates = _scan_strategy_live(
                    strategy, dm, long_syms, short_syms, nifty_today, today, want_long, want_short
                )
                for side, candidates in (("LONG", long_candidates), ("SHORT", short_candidates)):
                    if not candidates:
                        continue
                    picked = _pick_fillable_candidate(dm, name, side, candidates, symbol_registry)
                    if picked is None:
                        log.info(f"  {now_t.strftime('%H:%M')} — {name} {side}: no candidate cleared "
                                 f"the depth gate this cycle, will retry next bar")
                        continue
                    _place_trade(state, name, side, picked, now_t)
                    symbol_registry.claim(picked[0], side, name)

            if any_scanned:
                save_open_trades(today, state.snapshot())

        if state.any_open():
            _settle_fills_all(state, dm, now_t)
            _log_trade_monitor_all(state, dm)

        if now_t >= SQUARE_OFF:
            _force_time_exit_all(state, dm, today, now_t.strftime("%H:%M"))
            break


def _scan_strategy_live(strategy, dm: LiveDataManager, long_syms: set, short_syms: set,
                        nifty_today, trade_date: date, want_long: bool, want_short: bool):
    """
    Mirrors top10_backtest/engine.py::_scan_strategy, but pulling today/history/
    prev_day from LiveDataManager instead of preloaded slices. A BUY signal only
    counts if the symbol is in the LONG universe; a SELL signal only counts if
    it's in the SHORT (F&O) universe. Returns the FULL chronologically-sorted
    candidate list per side (not just the first) so the depth gate below can
    fall through to the next candidate if the first one is too thin to fill.
    """
    active = (long_syms if want_long else set()) | (short_syms if want_short else set())
    long_candidates, short_candidates = [], []

    for symbol in active:
        eligible_long  = want_long  and symbol in long_syms
        eligible_short = want_short and symbol in short_syms
        if not eligible_long and not eligible_short:
            continue

        today_5min = dm.get_today(symbol)
        if today_5min.empty:
            continue
        history_5min = dm.get_history(symbol)
        prev_day     = dm.get_prev_day(symbol)

        sig = strategy.generate_signal(today_5min, history_5min, prev_day, nifty_today, trade_date)
        if not sig.is_valid:
            continue

        strength = classify_strength(sig.direction, today_5min, history_5min, sig.signal_time)

        if sig.direction == 1 and eligible_long:
            long_candidates.append((symbol, today_5min, sig, strength))
        elif sig.direction == -1 and eligible_short:
            short_candidates.append((symbol, today_5min, sig, strength))

    key = lambda c: (c[2].signal_time or "99:99", c[0])
    return sorted(long_candidates, key=key), sorted(short_candidates, key=key)


def _pick_fillable_candidate(dm: LiveDataManager, strategy_name: str, side: str, candidates: list,
                             symbol_registry: SymbolSideRegistry):
    """
    Pre-trade gate: try candidates in chronological order, checking (a) cross-
    strategy symbol/side exclusivity and (b) live market depth BEFORE
    committing the day's slot. The first one clearing both wins; the rest are
    logged as skipped, not placed. Returns (symbol, today_5min, sig, strength,
    qty, notional, fc) or None if nothing in this cycle's candidate list
    qualifies.
    """
    for symbol, today_5min, sig, strength in candidates:
        if not symbol_registry.is_available(symbol, side, strategy_name):
            log.info(f"  SKIPPED [{side}] {strategy_name}: {symbol} | already taken {side} by another "
                     f"strategy today — trying next candidate")
            continue
        qty, notional = size(sig.entry)
        if qty <= 0:
            continue
        fc = check_fill(dm, symbol, sig.entry, qty, side, tolerance_pct=TOP10_FILL_TOLERANCE_PCT)
        ratio = fc["filled_qty"] / qty if qty else 0.0
        if fc["fillable"] is None or ratio >= TOP10_MIN_FILL_RATIO:
            return symbol, today_5min, sig, strength, qty, notional, fc
        log.info(f"  SKIPPED [{side}] {strategy_name}: {symbol} | only {fc['filled_qty']}/{qty} "
                 f"({ratio*100:.0f}%) fillable near Rs {sig.entry:.2f} — trying next candidate")
    return None


def _place_trade(state: Top10AgentState, strategy_name: str, side: str, picked: tuple, now_t) -> None:
    symbol, _today_5min, sig, strength, qty, notional, fc = picked

    rec = {
        "strategy":      strategy_name,
        "direction":     side,
        "symbol":        symbol,
        "signal":        sig.to_dict(),
        "entry_time":    now_t.strftime("%H:%M"),
        "shares":        qty,
        "position_rs":   notional,
        "move_strength": strength,
    }
    state.set(strategy_name, side, rec)
    log.info(
        f"PAPER TRADE PLACED [{side}] {strategy_name}: {symbol} | "
        f"signal_time={sig.signal_time} entry_time={rec['entry_time']} | "
        f"entry={sig.entry:.2f} target={sig.target:.2f} stop={sig.stop:.2f} | "
        f"size=Rs {notional:,.0f} ({qty} shares) | strength={strength}"
    )
    log.info(f"FILL CHECK   [{side}] {strategy_name}: {symbol} | {qty} shares @ Rs {sig.entry:.2f} | {fc['msg']}")
    rec["_fill_state"] = _init_fill_state(fc, qty)


# ─────────────────────────────────────────────────────────────────────────────
# Exit monitoring
# ─────────────────────────────────────────────────────────────────────────────

def _init_fill_state(fc: dict, target_shares: int) -> dict:
    return {
        "target_shares":  target_shares,
        "acc_filled":     fc["filled_qty"],
        "acc_weighted":   fc["avg_price"] * fc["filled_qty"] if fc["filled_qty"] > 0 else 0.0,
        "settled":        fc["fillable"] is True,
        "bars_remaining": 0 if fc["fillable"] is True else 1,
    }


def _settle_fills_all(state: Top10AgentState, dm: LiveDataManager, now_t) -> None:
    """
    Called each bar for open positions with unsettled fills. Below
    TOP10_MIN_FILL_RATIO at window close, the trade is VOIDED — closed with no
    P&L logged, and the strategy/side slot is freed for a later retry the
    same day — instead of being carried through to a fake full-size exit.
    Otherwise rec["shares"]/rec["position_rs"] are corrected to the ACTUAL
    filled quantity so P&L reflects what could really have been executed.
    """
    for strategy_name, side, rec in state.iter_open():
        fs = rec.get("_fill_state")
        if fs is None or fs["settled"]:
            continue

        fs["bars_remaining"] -= 1
        if fs["bars_remaining"] > 0:
            continue

        fs["settled"] = True
        symbol      = rec["symbol"]
        shares      = fs["target_shares"]
        entry_price = float(rec["signal"]["entry"])
        bar_str     = now_t.strftime("%H:%M")
        side_label  = "ask" if side == "LONG" else "bid"

        depth = dm.get_depth(symbol)
        if depth is not None:
            still_needed = shares - fs["acc_filled"]
            sim = simulate_fill(depth, still_needed, entry_price, side, TOP10_FILL_TOLERANCE_PCT)
            fs["acc_filled"] += sim["filled_qty"]
            if sim["filled_qty"] > 0:
                fs["acc_weighted"] += sim["avg_price"] * sim["filled_qty"]

        total_filled = fs["acc_filled"]
        avg_price    = fs["acc_weighted"] / total_filled if total_filled > 0 else 0.0
        ratio        = total_filled / shares if shares else 0.0

        if ratio < TOP10_MIN_FILL_RATIO:
            log.info(
                f"FILL VOID    [{side}] {strategy_name}: {symbol} | bar={bar_str} | "
                f"only {total_filled}/{shares} ({ratio*100:.0f}%) filled within window — "
                f"VOIDING trade, no P&L logged, slot freed for retry"
            )
            state.unplace(strategy_name, side)
            continue

        slip = (avg_price - entry_price if side == "LONG" else entry_price - avg_price)
        rec["_avg_fill_price"] = avg_price
        # Correct qty/notional to what could actually have been filled —
        # downstream P&L (log_closed_trade) uses rec["shares"]/rec["position_rs"].
        rec["shares"]      = total_filled
        rec["position_rs"] = round(total_filled * avg_price, 2)

        if total_filled >= shares:
            log.info(
                f"FILL SETTLE  [{side}] {strategy_name}: {symbol} | bar={bar_str} | "
                f"FULLY FILLED {shares:,} shares | avg Rs {avg_price:.2f} | "
                f"slippage Rs {slip:+.2f} vs signal entry Rs {entry_price:.2f}"
            )
        else:
            log.info(
                f"FILL SETTLE  [{side}] {strategy_name}: {symbol} | bar={bar_str} | "
                f"PARTIALLY FILLED {total_filled:,}/{shares} ({ratio*100:.0f}%) @ avg Rs {avg_price:.2f} | "
                f"proceeding at reduced size (insufficient depth at Rs {side_label})"
            )


_monitor_last_seen: dict[str, tuple[float, int]] = {}

def _log_trade_monitor_all(state: Top10AgentState, dm: LiveDataManager) -> None:
    for strategy_name, side, rec in state.iter_open():
        symbol     = rec["symbol"]
        last_price = dm.get_last_price(symbol)
        if last_price is None:
            continue
        entry  = float(rec["signal"]["entry"])
        target = float(rec["signal"]["target"])
        stop   = float(rec["signal"]["stop"])
        shares = rec["shares"]

        prev_price, stale_count = _monitor_last_seen.get(f"{strategy_name}_{side}_{symbol}", (None, 0))
        if prev_price is not None and last_price == prev_price:
            stale_count += 1
        else:
            stale_count = 0
        _monitor_last_seen[f"{strategy_name}_{side}_{symbol}"] = (last_price, stale_count)
        stale_tag = f"  *** STALE TICK ({stale_count + 1} bars) ***" if stale_count >= 1 else ""

        if side == "LONG":
            pnl = round((last_price - entry) * shares, 2)
        else:
            pnl = round((entry - last_price) * shares, 2)
        pnl_pct = round(pnl / (entry * shares) * 100, 2) if entry and shares else 0.0

        log.info(
            f"  MONITOR [{side}] {strategy_name} {symbol} @ {last_price:.2f} | "
            f"P&L Rs {pnl:+,.0f} ({pnl_pct:+.2f}%) | target={target:.2f} stop={stop:.2f}{stale_tag}"
        )


def _exit_fill_check(dm: LiveDataManager, strategy_name: str, side: str, symbol: str,
                     exit_price: float, shares: int) -> tuple[float, int]:
    """
    Verify the exit can actually execute near the trigger price — the exit-side
    counterpart to the entry pre-trade gate. Closing a LONG means SELLING
    (need buyers -> check the bid book, i.e. the same book-side logic
    check_fill uses for direction="SHORT"); closing a SHORT means BUYING BACK
    /covering (need sellers -> the ask book, direction="LONG"'s book side).
    So the exit direction passed to check_fill is the OPPOSITE of the
    position's own side.

    Returns (actual_exit_price, filled_qty). filled_qty < shares means the
    exit could not be fully completed near the trigger price — logged loudly
    as a real execution penalty, not silently absorbed.
    """
    exit_direction = "SHORT" if side == "LONG" else "LONG"
    verb           = "SOLD" if side == "LONG" else "BOUGHT"

    fc = check_fill(dm, symbol, exit_price, shares, exit_direction, tolerance_pct=TOP10_FILL_TOLERANCE_PCT)

    if fc["fillable"] is None:
        log.info(f"EXIT FILL    [{side}] {strategy_name}: {symbol} | depth unavailable — "
                 f"{verb} {shares}/{shares} assumed @ Rs {exit_price:.2f} (unverified)")
        return exit_price, shares

    filled_qty = fc["filled_qty"]
    avg_price  = fc["avg_price"]
    best_qty   = fc["best_qty"]
    best_avg   = fc["best_avg"]

    if filled_qty >= shares:
        log.info(f"EXIT FILL    [{side}] {strategy_name}: {symbol} | {verb} {shares}/{shares} "
                 f"@ avg Rs {avg_price:.2f} — FULL EXIT, no penalty")
        return avg_price, shares

    if best_qty >= shares:
        penalty = round(abs(exit_price - best_avg) * shares, 2)
        log.warning(f"EXIT FILL    [{side}] {strategy_name}: {symbol} | only {filled_qty}/{shares} "
                    f"near trigger Rs {exit_price:.2f} — chased to avg Rs {best_avg:.2f} to close in full "
                    f"— PENALTY Rs {penalty:,.2f}")
        return best_avg, shares

    # Can't fully close even walking the entire book — rare, but must be visible.
    fallback_price = best_avg if best_qty > 0 else exit_price
    log.error(f"EXIT FILL    [{side}] {strategy_name}: {symbol} | {verb} only {best_qty}/{shares} "
              f"even at best available price — INCOMPLETE EXIT, accounted @ Rs {fallback_price:.2f} "
              f"for all {shares} shares (real slippage may exceed what's modeled here)")
    return fallback_price, best_qty if best_qty > 0 else shares


def _check_exit_all(state: Top10AgentState, dm: LiveDataManager, today: date) -> None:
    """
    Called on every tick batch. Target checked before stop, same order as the
    backtest's _simulate_outcome — no profit-lock, matching the backtest exactly.
    """
    now_str = _now_ist().strftime("%H:%M")
    changed = False

    for strategy_name, side, rec in state.iter_open():
        symbol = rec["symbol"]
        target = float(rec["signal"]["target"])
        stop   = float(rec["signal"]["stop"])
        last_price = dm.get_last_price(symbol)
        if last_price is None:
            continue

        if side == "LONG":
            target_hit = last_price >= target
            stop_hit   = last_price <= stop
        else:
            target_hit = last_price <= target
            stop_hit   = last_price >= stop

        if target_hit:
            log.info(f"TARGET HIT [{side}] {strategy_name}: {symbol} @ {last_price:.2f} (target={target:.2f})")
            state.close(strategy_name, side)
            actual_price, filled_qty = _exit_fill_check(dm, strategy_name, side, symbol, target, rec["shares"])
            log_closed_trade(today, strategy_name, side, rec, exit_price=actual_price,
                             exit_reason="TARGET_HIT", exit_time=now_str, exit_qty_filled=filled_qty)
            changed = True
        elif stop_hit:
            log.info(f"STOP HIT [{side}] {strategy_name}: {symbol} @ {last_price:.2f} (stop={stop:.2f})")
            state.close(strategy_name, side)
            actual_price, filled_qty = _exit_fill_check(dm, strategy_name, side, symbol, stop, rec["shares"])
            log_closed_trade(today, strategy_name, side, rec, exit_price=actual_price,
                             exit_reason="STOP_HIT", exit_time=now_str, exit_qty_filled=filled_qty)
            changed = True

    if changed:
        save_open_trades(today, state.snapshot())


def _force_time_exit_all(state: Top10AgentState, dm: LiveDataManager, today: date, exit_time: str) -> None:
    """Force-close every still-open position at 3:15 PM."""
    if not state.any_placed():
        log.info("No trades placed today — no exit needed")
        return

    open_positions = state.iter_open()
    if not open_positions:
        log.info("All positions already closed before square-off")
    for strategy_name, side, rec in open_positions:
        symbol = rec["symbol"]
        last_price = dm.get_last_price(symbol)
        if last_price is None:
            last_price = float(rec["signal"]["entry"])
            log.warning(f"  No live price for {symbol} — using entry price as exit")
        log.info(f"TIME EXIT [{side}] {strategy_name}: {symbol} @ {last_price:.2f} (3:15 PM square-off)")
        state.close(strategy_name, side)
        actual_price, filled_qty = _exit_fill_check(dm, strategy_name, side, symbol, last_price, rec["shares"])
        log_closed_trade(today, strategy_name, side, rec, exit_price=actual_price,
                         exit_reason="TIME_EXIT", exit_time=exit_time, exit_qty_filled=filled_qty)

    save_open_trades(today, state.snapshot())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_ist() -> datetime:
    return datetime.now(IST)


def _next_bar_close(now: datetime) -> datetime:
    minute  = now.minute
    seconds = now.second + now.microsecond / 1e6
    offset  = 5 - (minute % 5)
    if offset == 5 and seconds < 1:
        offset = 5
    next_dt = now.replace(second=0, microsecond=0) + timedelta(minutes=offset)
    return next_dt


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live Paper Trading Agent — Top-10 Strategy Roster")
    p.add_argument("--token", metavar="ACCESS_TOKEN", help="Broker access token for today")
    p.add_argument("--broker", default="zerodha", help="Broker to use: zerodha (default) or groww")
    return p.parse_args()


def _print_summary(state: Top10AgentState, today: date) -> None:
    log.info("")
    log.info("=" * 65)
    log.info(f"  Day summary — {today}")
    snap = state.snapshot()
    any_placed = any(s["long_placed"] or s["short_placed"] for s in snap.values())
    if not any_placed:
        log.info("  No trades placed today")
    for name, s in snap.items():
        if not s["long_placed"] and not s["short_placed"]:
            continue
        for side_key, label in (("long", "LONG"), ("short", "SHORT")):
            if not s[f"{side_key}_placed"]:
                continue
            rec = s[side_key]
            if rec is None:
                log.info(f"  [{name} {label}] trade placed and closed — see top10_live_trades.csv")
            else:
                sig = rec["signal"]
                log.info(f"  [{name} {label}] {rec['symbol']} | entry={sig['entry']:.2f} "
                         f"target={sig['target']:.2f} stop={sig['stop']:.2f} | "
                         f"size=Rs {rec['position_rs']:,.0f}")
                log.info(f"    WARNING: position not closed — check top10_live_open_trades.json")
    log.info("=" * 65)


if __name__ == "__main__":
    main()

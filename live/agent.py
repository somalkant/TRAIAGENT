"""
Live Paper Trading Agent — Phase 2.5

Daily usage (run before 9:15 AM):
    python live/agent.py --token YOUR_KITE_ACCESS_TOKEN

What it does each day:
  PRE-MARKET  (9:00 – 9:14 AM)
    1. Authenticate with Kite using today's access token
    2. Fetch NSE instrument list → build symbol-to-token map
    3. Run pre-market filter on parquet history → top 25 watchlist stocks
    4. Load 30-day 5-min history from parquet for watchlist stocks
    5. Connect KiteTicker, subscribe all 25 tokens + Nifty50
    6. Wait for 9:15 AM market open

  MARKET HOURS (9:15 AM – 2:00 PM)
    Every 5-min bar close:
      - close_bar() on all candle builders
      - run scan_once() across watchlist
      - If a recommendation passes all filters → log entry, monitor for exit

  EXIT MONITORING (after trade is placed → 3:15 PM)
    - KiteTicker on_ticks() checks live price against target / stop
    - TARGET_HIT or STOP_HIT → log closed trade immediately
    - 3:15 PM TIME_EXIT → log at last traded price

  POST-MARKET (3:15 PM)
    - Print day summary
    - Disconnect KiteTicker
    - Exit

Crash safety:
  - Open trade state is checkpointed to checkpoints/live_open_trade.json
  - Restart the agent with the same token — it resumes monitoring the open trade

How to get the access token:
  1. Run: python -c "from data_pipeline.kite_auth import login_step1; login_step1()"
  2. Open the printed URL, log in to Zerodha
  3. Copy the request_token from the redirect URL
  4. Run: python -c "from data_pipeline.kite_auth import login_step2; login_step2('YOUR_REQUEST_TOKEN')"
  5. Find your access_token in checkpoints/access_token.json
  OR simply pass --token directly if you already have today's access token.
"""

import argparse
import json
import logging
import threading
import time as time_mod
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path

import pytz

import pandas as pd

_IST = pytz.timezone("Asia/Kolkata")

def _to_ist(series: pd.Series) -> pd.Series:
    """Convert a datetime Series to IST-naive (09:15, not 03:45).
    Matches CandleBuilder bar labels so history concat stays in order."""
    dt = pd.to_datetime(series)
    if dt.dt.tz is not None:
        return dt.dt.tz_convert(_IST).dt.tz_localize(None)
    return dt

# kiteconnect imported lazily inside main() — importing it at module level can
# hang on Python 3.13 due to SSL/WebSocket initialisation during import.
# from kiteconnect import KiteConnect, KiteTicker  ← moved to main()

from config.settings import (
    WEIGHTS_FILE, PROFIT_LOCK_ENABLED, PROFIT_LOCK_TRIGGER_PCT, PROFIT_LOCK_TRAIL_PCT,
    NEWS_ENABLED,
)
from live.instrument_map import load_instrument_map, NIFTY50_TOKEN
from live.data_manager import LiveDataManager
from live.live_engine import scan_once
from live.paper_logger import (
    save_open_trade, load_open_trade, log_closed_trade
)
from live.news_signal import assess_news, company_name_for
from live.risk_guard import check_risk_limits, write_eod_risk_check
from live.fill_check import check_fill, simulate_fill, check_exit_fill
from watchlist.pre_filter import PreMarketFilter

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

IST         = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
NO_ENTRY    = dtime(14, 0)    # no new positions after 2:00 PM
SQUARE_OFF  = dtime(15, 15)   # force exit at 3:15 PM


# ─────────────────────────────────────────────────────────────────────────────
# Agent state (shared between main thread and KiteTicker callback thread)
# ─────────────────────────────────────────────────────────────────────────────

class AgentState:
    """Tracks up to one open LONG and one open SHORT position per day."""

    def __init__(self):
        self._long:         dict | None = None   # None = no LONG placed or already closed
        self._short:        dict | None = None   # None = no SHORT placed or already closed
        self._long_placed:  bool        = False  # True once any LONG was placed today
        self._short_placed: bool        = False  # True once any SHORT was placed today
        self._lock = threading.Lock()

    def set_long(self, rec: dict) -> None:
        with self._lock:
            self._long        = rec
            self._long_placed = True

    def set_short(self, rec: dict) -> None:
        with self._lock:
            self._short        = rec
            self._short_placed = True

    def close_long(self) -> None:
        with self._lock:
            self._long = None

    def close_short(self) -> None:
        with self._lock:
            self._short = None

    def close_long_if_current(self, rec: dict) -> bool:
        """
        Atomic check-and-close: only clears the LONG slot (and returns True) if
        it still holds this exact rec object. Prevents a duplicate exit log when
        two tick callbacks race past the exit check before either has closed the
        position (observed live as a double-logged trade during a ticker reconnect).
        """
        with self._lock:
            if self._long is rec:
                self._long = None
                return True
            return False

    def close_short_if_current(self, rec: dict) -> bool:
        with self._lock:
            if self._short is rec:
                self._short = None
                return True
            return False

    def is_long_open(self) -> bool:
        with self._lock:
            return self._long is not None

    def is_short_open(self) -> bool:
        with self._lock:
            return self._short is not None

    def snapshot(self) -> tuple[dict | None, dict | None, bool, bool]:
        """Return (long_rec, short_rec, long_placed, short_placed) atomically."""
        with self._lock:
            return self._long, self._short, self._long_placed, self._short_placed


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = _parse_args()
    today = date.today()

    log.info("=" * 65)
    log.info(f"  Live Paper Trading Agent — Phase 2.5 — {today}")
    log.info("=" * 65)

    # ── 1. Authenticate ─────────────────────────────────────────────────────
    # Broker is imported lazily to avoid kiteconnect's SSL/WebSocket init hang.
    from brokers import get_broker  # noqa: PLC0415
    broker = get_broker(args.broker)
    log.info(f"Loading {broker.display_name} API classes...")
    KiteConnect, KiteTicker = broker.get_api_classes()

    api_key, access_token = broker.get_credentials(args)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    log.info(f"{broker.display_name} authenticated successfully")

    # ── 2. Instrument map ───────────────────────────────────────────────────
    imap = load_instrument_map(kite, args.broker)

    # ── 2b. Gap-fill — download any missed EOD data before loading history ──
    # If yesterday's EOD was not downloaded (e.g. ran Groww but EOD was
    # Zerodha-only, or agent was stopped before 15:31), fill the gap now
    # using the active broker.  Returns instantly when parquets are current.
    _fill_parquet_gaps(kite, imap, today)

    # ── 3. Load frozen WF weights ────────────────────────────────────────────
    weights = _load_weights(args.wf_window)
    log.info(f"Loaded WF{args.wf_window} frozen weights ({len(weights)} strategies)")

    # ── 3b. Risk limits check — exits if monthly/daily halt flag is active ──
    check_risk_limits(today)

    # ── 4. Load history + pre-market filter → watchlist ────────────────────
    # Load parquet history for ALL universe stocks — needed so the pre-market filter
    # can score the full 500-stock universe and return the top 25.
    universe_symbols = _load_universe_symbols()
    log.info(f"Universe: {len(universe_symbols)} stocks — loading parquet history...")
    all_history = _load_history_for_symbols(universe_symbols, today)
    log.info(f"History loaded for {len(all_history)} symbols")

    # Run pre-market filter → top 25 watchlist
    pre_filter  = PreMarketFilter()
    watchlist   = pre_filter.build(today, all_history)
    wl_symbols  = [e["symbol"] for e in watchlist]
    log.info(f"Watchlist ({len(wl_symbols)}): {', '.join(wl_symbols)}")

    # Save full watchlist so test_single_day and post-market review can load it
    from watchlist.pre_filter import save_watchlist
    save_watchlist(watchlist, today)

    # ── 5. Data manager — reuse already-loaded history, don't reload from parquet ──
    dm = LiveDataManager(symbols=wl_symbols, imap=imap)
    for sym in wl_symbols:
        if sym in all_history:
            dm._history[sym] = all_history[sym]
    dm._load_nifty_history([today.year - 1, today.year], today)
    # Release non-watchlist history to free memory
    del all_history

    # ── 5b. Resume today's candle bars if agent was restarted mid-day ────────
    dm.resume_from_checkpoint(today)

    # ── 5c. Late start: backfill today's bars from Kite API if market is open ─
    # Runs when the agent starts (or restarts) after 9:20 AM and candle history
    # is incomplete — either no checkpoint (fresh late start) or checkpoint only
    # has bars from a mid-day session (not from 9:15 AM).
    now_ist = _now_ist()
    if now_ist.time() > dtime(9, 20):
        # How many 5-min bars should have closed since 9:15 AM?
        market_open_dt = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        last_closed_t  = now_ist.replace(
            minute=(now_ist.minute // 5) * 5, second=0, microsecond=0
        ) - timedelta(minutes=5)
        expected_bars = max(0, int((last_closed_t - market_open_dt).total_seconds() / 300) + 1)

        # How many bars do we actually have? (use the most-populated symbol)
        actual_bars = max(
            (len(dm._builders[s].closed_bars) for s in dm.symbols[:5]
             if dm._builders[s].closed_bars),
            default=0,
        )

        if expected_bars > 0 and actual_bars < expected_bars * 0.8:
            log.info(
                f"Candle history incomplete: {actual_bars} bars vs {expected_bars} expected "
                f"— backfilling from Kite API"
            )
            _backfill_today_bars(kite, dm, today)

    # ── 6. Check if there's a crash-recovered open trade from today ─────────
    state = AgentState()
    _, long_rec, short_rec = load_open_trade()
    if long_rec:
        state.set_long(long_rec)
        log.info(f"RECOVERED open LONG:  {long_rec['symbol']} — monitoring for exit")
    if short_rec:
        state.set_short(short_rec)
        log.info(f"RECOVERED open SHORT: {short_rec['symbol']} — monitoring for exit")

    # ── 7. Ticker WebSocket setup ────────────────────────────────────────────
    tokens     = dm.instrument_tokens
    _last_tick = [None]   # [datetime | None] — updated on every tick; mutable so closure can write
    _ws_holder = [None]   # [current ws] — swapped on reconnect

    log.info(f"Subscribing {len(tokens)} instrument tokens to {broker.display_name} ticker")

    def _make_ticker():
        """Create, wire, and start a fresh ticker. Called at startup and on reconnect."""
        try:
            # Zerodha KiteTicker supports reconnect=True natively (default 50 retries).
            # Groww GrowwTickerAdapter ignores unknown kwargs — safe to pass.
            new_ws = KiteTicker(api_key, access_token, reconnect=True, reconnect_max_tries=50)
        except TypeError:
            new_ws = KiteTicker(api_key, access_token)

        def on_connect(ws, _response):
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            log.info(f"{broker.display_name} ticker connected and subscribed")

        def on_ticks(_ws, ticks):
            # Staleness clock counts STOCK ticks only — the Nifty index arrives via
            # an independent REST poll that can stay alive while the stock feed is
            # dead, which would otherwise mask the outage from the reconnect sweep.
            if any(t.get("instrument_token") != NIFTY50_TOKEN for t in ticks):
                _last_tick[0] = datetime.now()
            for tick in ticks:
                dm.on_tick(tick)
            if state.is_long_open() or state.is_short_open():
                _check_exit(state, dm, today)

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
        _run_market_loop(_ws_holder, _last_tick, _make_ticker, dm, state, weights, today)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        if _ws_holder[0]:
            _ws_holder[0].close()
        log.info("Ticker disconnected. Agent stopped.")

    # ── 9. Day summary ───────────────────────────────────────────────────────
    _print_summary(state, today)

    # ── 10. Post-market EOD data download ────────────────────────────────────
    _run_eod_download(kite, imap, today)


# ─────────────────────────────────────────────────────────────────────────────
# Market loop — runs in main thread
# ─────────────────────────────────────────────────────────────────────────────

_TICKER_STALE_SECS = 300   # warn + reconnect if no tick for 5 minutes during market hours

def _run_market_loop(ws_holder: list, last_tick: list, make_ticker,
                     dm: LiveDataManager, state: AgentState,
                     weights: dict, today: date) -> None:
    """
    Main scheduling loop.
    Sleeps until the next 5-min bar boundary, then:
      - Closes the bar on all candle builders
      - If no trade yet and time < 2 PM: runs scan_once()
      - If signal found: saves and monitors it
      - Checks ticker staleness — reconnects if no tick for 5+ minutes
      - At 3:15 PM: forces TIME_EXIT and exits loop
    """
    while True:
        now     = _now_ist()
        now_t   = now.time()

        # Post-market — done
        if now_t >= SQUARE_OFF:
            _force_time_exit(state, dm, today, now_t.strftime("%H:%M"))
            break

        # Wait for next 5-min bar boundary
        next_bar_dt = _next_bar_close(now)
        sleep_secs  = (next_bar_dt - now).total_seconds() + 0.3  # 0.3s grace — enough for last ticks, avoids bleeding next bar data

        if sleep_secs > 0:
            time_mod.sleep(sleep_secs)

        # Recalculate now after sleep
        now   = _now_ist()
        now_t = now.time()

        if now_t < MARKET_OPEN:
            continue   # still pre-market, keep waiting

        # ── Ticker staleness check ───────────────────────────────────────────
        # If no tick has arrived for 5+ minutes during market hours, the
        # WebSocket has silently died. Close and restart a fresh connection.
        if MARKET_OPEN <= now_t < SQUARE_OFF and last_tick[0] is not None:
            age = (datetime.now() - last_tick[0]).total_seconds()
            if age > _TICKER_STALE_SECS:
                log.warning(
                    f"Ticker stale: no ticks for {age:.0f}s — reconnecting..."
                )
                try:
                    ws_holder[0].close()
                except Exception:
                    pass
                time_mod.sleep(2)
                try:
                    ws_holder[0] = make_ticker()
                    last_tick[0] = datetime.now()   # reset clock; on_ticks will update
                    log.info("Ticker reconnected successfully")
                except Exception as e:
                    log.error(f"Ticker reconnect failed: {e} — will retry next bar")

        # Close the completed 5-min bar
        bar_label = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
        bar_label = bar_label.replace(tzinfo=None)  # strip tz for DataFrame compatibility
        if bar_label.time() < MARKET_OPEN:
            continue  # first wake at 09:15 gives bar_label=09:10 (pre-open) — skip it
        dm.close_bar(bar_label)
        log.debug(f"Bar closed: {bar_label.strftime('%H:%M')}")

        # Scan per-direction — one trade per direction per day (matches backtester rule)
        long_snap, short_snap, long_placed, short_placed = state.snapshot()
        need_long  = long_snap  is None and not long_placed  and now_t < NO_ENTRY
        need_short = short_snap is None and not short_placed and now_t < NO_ENTRY

        if need_long or need_short:
            recs = scan_once(dm, weights, today,
                             want_long=need_long, want_short=need_short)
            placed_any = False
            for rec in recs:
                dirn = rec["direction"]
                if dirn == "LONG" and not state.is_long_open():
                    state.set_long(rec)
                    placed_any = True
                    log.info(
                        f"PAPER TRADE PLACED [LONG]:  {rec['symbol']} | "
                        f"signal_time={rec['signal']['signal_time']} "
                        f"entry_time={rec.get('entry_time', now_t.strftime('%H:%M'))} | "
                        f"entry={rec['signal']['entry']:.2f} "
                        f"target={rec['signal']['target']:.2f} "
                        f"stop={rec['signal']['stop']:.2f} | "
                        f"size=Rs {rec['position_rs']:,.0f} ({rec['shares']} shares)"
                    )
                    fc = check_fill(dm, rec["symbol"],
                                    rec["signal"]["entry"], rec["shares"], "LONG")
                    log.info(
                        f"FILL CHECK   [LONG]:  {rec['symbol']} | "
                        f"signal={rec['signal']['signal_time']} "
                        f"entry={rec.get('entry_time', now_t.strftime('%H:%M'))} | "
                        f"{rec['shares']} shares @ ₹{rec['signal']['entry']:.2f} | "
                        f"{fc['msg']}"
                    )
                    rec["_fill_state"] = _init_fill_state(fc, rec["shares"])
                    _attach_news(rec, "LONG", today)
                elif dirn == "SHORT" and not state.is_short_open():
                    state.set_short(rec)
                    placed_any = True
                    log.info(
                        f"PAPER TRADE PLACED [SHORT]: {rec['symbol']} | "
                        f"signal_time={rec['signal']['signal_time']} "
                        f"entry_time={rec.get('entry_time', now_t.strftime('%H:%M'))} | "
                        f"entry={rec['signal']['entry']:.2f} "
                        f"target={rec['signal']['target']:.2f} "
                        f"stop={rec['signal']['stop']:.2f} | "
                        f"size=Rs {rec['position_rs']:,.0f} ({rec['shares']} shares)"
                    )
                    fc = check_fill(dm, rec["symbol"],
                                    rec["signal"]["entry"], rec["shares"], "SHORT")
                    log.info(
                        f"FILL CHECK   [SHORT]: {rec['symbol']} | "
                        f"signal={rec['signal']['signal_time']} "
                        f"entry={rec.get('entry_time', now_t.strftime('%H:%M'))} | "
                        f"{rec['shares']} shares @ ₹{rec['signal']['entry']:.2f} | "
                        f"{fc['msg']}"
                    )
                    rec["_fill_state"] = _init_fill_state(fc, rec["shares"])
                    _attach_news(rec, "SHORT", today)
            if placed_any:
                long_rec, short_rec, _, _ = state.snapshot()
                save_open_trade(today, long_rec, short_rec)
            else:
                dirs = []
                if need_long:  dirs.append("LONG")
                if need_short: dirs.append("SHORT")
                log.info(f"  {now_t.strftime('%H:%M')} — no signal for {'/'.join(dirs)}")

        if state.is_long_open() or state.is_short_open():
            _settle_fills(state, dm, now_t)
            _log_trade_monitor(state, dm)

        # Intraday 3:15 PM check
        if now_t >= SQUARE_OFF:
            _force_time_exit(state, dm, today, now_t.strftime("%H:%M"))
            break


def _attach_news(rec: dict, direction: str, trade_date) -> None:
    """
    MONITOR ONLY (Phase 2.7): assess yesterday's/today's news for the just-placed
    trade and emit one NEWS log line. The result is attached to rec['news'] so it
    persists in the open-trade checkpoint and can be written to the trade log at
    exit (Phase 3). This NEVER affects the trade — assess_news() returns a
    well-formed UNAVAILABLE dict on any failure and cannot raise.

    Runs synchronously on the placement bar (1-2x/day, ~3s). Exit monitoring runs
    on the WebSocket tick thread, so this brief pause never delays an exit.
    """
    if not NEWS_ENABLED:
        return
    try:
        company = company_name_for(rec["symbol"])
        ns = assess_news(rec["symbol"], company, direction, trade_date)
        rec["news"] = ns
        log.info(
            f"NEWS [{direction}]: {rec['symbol']} | "
            f"{ns['news_signal']} (score {ns['news_score']:+.2f}, "
            f"conf {ns['news_conf']:.2f}, {ns['news_count']} items) | "
            f"\"{ns['news_headline']}\" | src={ns['news_source']}"
        )
    except Exception as e:                       # noqa: BLE001 — belt-and-suspenders
        log.warning(f"NEWS [{direction}]: {rec.get('symbol')} — skipped ({e})")


# ─────────────────────────────────────────────────────────────────────────────
# Exit monitoring
# ─────────────────────────────────────────────────────────────────────────────

def _init_fill_state(fc: dict, target_shares: int) -> dict:
    """Create fill tracking state from the initial check_fill() result."""
    return {
        "target_shares":  target_shares,
        "acc_filled":     fc["filled_qty"],
        "acc_weighted":   fc["avg_price"] * fc["filled_qty"] if fc["filled_qty"] > 0 else 0.0,
        "settled":        fc["fillable"] is True,   # already complete if FILLED at placement
        "bars_remaining": 0 if fc["fillable"] is True else 1,  # check once more next bar
    }


def _settle_fills(state: AgentState, dm: LiveDataManager, now_t) -> None:
    """
    Called each bar for open positions with unsettled fills.
    On the bar immediately after placement (+5 min window):
      - Re-queries live depth
      - Simulates book-walk to compute avg fill price and remaining qty
      - Logs FILL SETTLE with final verdict and slippage vs signal entry
    """
    long_rec, short_rec, _, _ = state.snapshot()
    for rec in (long_rec, short_rec):
        if rec is None:
            continue
        fs = rec.get("_fill_state")
        if fs is None or fs["settled"]:
            continue

        # Count down the remaining bars in the fill window
        fs["bars_remaining"] -= 1
        if fs["bars_remaining"] > 0:
            continue   # still within window, wait one more bar

        # Window expired — take one final depth snapshot and log
        fs["settled"] = True
        symbol      = rec["symbol"]
        direction   = rec["direction"]
        shares      = fs["target_shares"]
        entry_price = float(rec["signal"]["entry"])
        bar_str     = now_t.strftime("%H:%M")
        side        = "ask" if direction == "LONG" else "bid"

        depth = dm.get_depth(symbol)
        if depth is None:
            log.info(
                f"FILL SETTLE  [{direction}]: {symbol} | bar={bar_str} | "
                f"depth unavailable — cannot confirm fill"
            )
            return

        # Check what's available NOW at entry_price
        still_needed = shares - fs["acc_filled"]
        sim = simulate_fill(depth, still_needed, entry_price, direction)

        # Accumulate into running totals
        fs["acc_filled"]   += sim["filled_qty"]
        if sim["filled_qty"] > 0:
            fs["acc_weighted"] += sim["avg_price"] * sim["filled_qty"]

        total_filled = fs["acc_filled"]
        avg_price    = fs["acc_weighted"] / total_filled if total_filled > 0 else 0.0
        slip         = (avg_price - entry_price if direction == "LONG"
                        else entry_price - avg_price)

        if total_filled >= shares:
            rec["_avg_fill_price"] = avg_price
            log.info(
                f"FILL SETTLE  [{direction}]: {symbol} | bar={bar_str} | "
                f"FULLY FILLED {shares:,} shares | avg ₹{avg_price:.2f} | "
                f"slippage ₹{slip:+.2f} vs signal entry ₹{entry_price:.2f}"
            )
        else:
            # Still not fully filled — show what best available price would achieve
            best_still = sim["best_qty"]
            could_fill = (total_filled + best_still) >= shares
            if could_fill and sim["best_price"] is not None:
                total_best_filled = total_filled + best_still
                best_wsum = fs["acc_weighted"] + (sim["best_avg"] * best_still if best_still > 0 else 0)
                best_avg_total = best_wsum / total_best_filled if total_best_filled > 0 else 0.0
                best_slip = (best_avg_total - entry_price if direction == "LONG"
                             else entry_price - best_avg_total)
                best_note = (
                    f"at best {side} ₹{sim['best_price']:.2f}: FILLS @ avg ₹{best_avg_total:.2f} "
                    f"(slip ₹{best_slip:+.2f})"
                )
            else:
                best_note = f"insufficient depth even at best {side}"

            partial_str = f"{total_filled:,}/{shares}" if total_filled > 0 else f"0/{shares}"
            avg_str     = f" @ avg ₹{avg_price:.2f}" if total_filled > 0 else ""
            log.info(
                f"FILL SETTLE  [{direction}]: {symbol} | bar={bar_str} | "
                f"NOT FILLED within 5-min window — {partial_str} shares{avg_str} | {best_note}"
            )


_monitor_last_seen: dict[str, tuple[float, int]] = {}  # symbol -> (price, consecutive_unchanged_bars)

def _log_trade_monitor(state: AgentState, dm: LiveDataManager) -> None:
    """Log current price and unrealised P&L every 5-min bar for each open position."""
    long_rec, short_rec, _, _ = state.snapshot()
    for rec in (long_rec, short_rec):
        if rec is None:
            continue
        symbol     = rec["symbol"]
        direction  = rec.get("direction", "LONG")
        last_price = dm.get_last_price(symbol)
        if last_price is None:
            continue
        entry  = float(rec["signal"]["entry"])
        target = float(rec["signal"]["target"])
        stop   = float(rec["signal"]["stop"])
        shares = rec["shares"]

        # Staleness detector: warn if price unchanged for 2+ consecutive bars
        prev_price, stale_count = _monitor_last_seen.get(symbol, (None, 0))
        if prev_price is not None and last_price == prev_price:
            stale_count += 1
        else:
            stale_count = 0
        _monitor_last_seen[symbol] = (last_price, stale_count)
        stale_tag = f"  *** STALE TICK — price unchanged for {stale_count + 1} bars ***" if stale_count >= 1 else ""

        if direction == "LONG":
            pnl       = round((last_price - entry) * shares, 2)
            pnl_pct   = round((last_price - entry) / entry * 100, 2)
            to_target = round((target - last_price) / last_price * 100, 2)
            to_stop   = round((last_price - stop)   / last_price * 100, 2)
        else:
            pnl       = round((entry - last_price) * shares, 2)
            pnl_pct   = round((entry - last_price) / entry * 100, 2)
            to_target = round((last_price - target) / last_price * 100, 2)
            to_stop   = round((stop - last_price)   / last_price * 100, 2)

        log.info(
            f"  MONITOR [{direction}] {symbol} @ {last_price:.2f} | "
            f"P&L Rs {pnl:+,.0f} ({pnl_pct:+.2f}%) | "
            f"to_target={to_target:+.2f}% to_stop={to_stop:+.2f}%{stale_tag}"
        )
        if stale_count >= 1:
            log.warning(f"  STALE TICK [{symbol}]: WebSocket may have dropped — exit checks unreliable")


def _update_profit_lock(rec: dict, direction: str, last_price: float) -> None:
    """
    Trailing profit-lock: track the best (most favorable) price seen since entry;
    once PROFIT_LOCK_TRIGGER_PCT favorable move is reached, ratchet the stop to
    trail PROFIT_LOCK_TRAIL_PCT behind that peak. The stop only ever tightens,
    never loosens, so this can only reduce risk versus the original stop.

    Replaying the 36 real live trades against actual bars showed a hard
    "+1.0% -> lock +0.7%" jump reduces net P&L (it kills the target-hit tail);
    this wider trailing version was ~neutral to slightly better and would have
    converted the worst single loss (a trade that ran to +1.77% before reversing
    to a full stop) into a small winner.
    """
    entry = float(rec["signal"]["entry"])
    if entry <= 0:
        return
    prev_peak = rec.get("_peak_price", entry)
    peak = max(prev_peak, last_price) if direction == "LONG" else min(prev_peak, last_price)
    rec["_peak_price"] = peak

    mfe_pct = ((peak - entry) / entry * 100) if direction == "LONG" else ((entry - peak) / entry * 100)
    if mfe_pct < PROFIT_LOCK_TRIGGER_PCT:
        return

    cur_stop = float(rec["signal"]["stop"])
    if direction == "LONG":
        trail_stop = round(peak * (1 - PROFIT_LOCK_TRAIL_PCT / 100), 2)
        if trail_stop > cur_stop:
            rec["signal"]["stop"] = trail_stop
            rec["_profit_locked"] = True
            log.info(f"PROFIT LOCK [LONG]: {rec['symbol']} | peak={peak:.2f} (mfe={mfe_pct:.2f}%) | "
                     f"stop {cur_stop:.2f} -> {trail_stop:.2f}")
    else:
        trail_stop = round(peak * (1 + PROFIT_LOCK_TRAIL_PCT / 100), 2)
        if trail_stop < cur_stop:
            rec["signal"]["stop"] = trail_stop
            rec["_profit_locked"] = True
            log.info(f"PROFIT LOCK [SHORT]: {rec['symbol']} | peak={peak:.2f} (mfe={mfe_pct:.2f}%) | "
                     f"stop {cur_stop:.2f} -> {trail_stop:.2f}")


def _exit_ref_price(dm: LiveDataManager, symbol: str, direction: str,
                    fallback_price: float) -> tuple[float, str]:
    """
    The price a real close would actually execute at right now: best bid for
    closing a LONG (you're selling), best ask for covering a SHORT (you're
    buying). Falls back to the last-traded tick (fallback_price) when depth
    isn't available yet or that side of the book is empty.

    Exit decisions (stop/target triggers, profit-lock peak tracking) use this
    instead of the raw LTP tick. Fixes a class of premature stop-outs where a
    single LTP print is stale, off-market, or an odd-lot execution that the
    live order book has already moved past — observed live: INDUSINDBK
    2026-07-21 09:36 — an LTP tick of 1050.45 triggered a 1050.87 profit-lock
    stop, but the book's best bid at that same instant was 1051.60 (above the
    stop) — a real sell there would not have been stopped out.
    """
    depth = dm.get_depth(symbol) if hasattr(dm, "get_depth") else None
    if depth:
        book_key = "buy" if direction == "LONG" else "sell"
        levels = depth.get(book_key) or []
        if levels:
            return float(levels[0]["price"]), "book"
    return fallback_price, "ltp"


def _check_exit(state: AgentState, dm: LiveDataManager, today: date) -> None:
    """
    Called on every tick (from broker WebSocket callback).
    Checks target/stop independently for the open LONG and open SHORT position.
    """
    now_str = _now_ist().strftime("%H:%M")
    changed = False
    lock_updated = False
    long_rec, short_rec, _, _ = state.snapshot()

    for rec, close_fn in ((long_rec, state.close_long_if_current), (short_rec, state.close_short_if_current)):
        if rec is None:
            continue
        symbol    = rec["symbol"]
        direction = rec.get("direction", "LONG")
        target    = float(rec["signal"]["target"])
        last_price = dm.get_last_price(symbol)
        if last_price is None:
            continue

        # Book-corroborated decision price — see _exit_ref_price docstring.
        ref_price, ref_source = _exit_ref_price(dm, symbol, direction, last_price)

        # Skip redundant reprocessing: the feed can redeliver an identical
        # (LTP, book-price) pair many times in a burst — observed live on
        # BOSCHLTD 2026-07-22, ~1,000 duplicate "TARGET CHECK" log lines in
        # one session, tied to repeated NATS reconnects replaying a backlog.
        # If BOTH prices are bit-identical to the last check we actually
        # acted on, nothing about the trade's state can have changed, so it's
        # safe to skip the profit-lock update, the trigger check, and the log
        # line — any genuine change in either price still runs the full
        # check exactly as before.
        dedup_key = (last_price, ref_price)
        if rec.get("_last_checked") == dedup_key:
            continue
        rec["_last_checked"] = dedup_key

        if PROFIT_LOCK_ENABLED:
            stop_before = float(rec["signal"]["stop"])
            _update_profit_lock(rec, direction, ref_price)
            if float(rec["signal"]["stop"]) != stop_before:
                lock_updated = True

        stop = float(rec["signal"]["stop"])   # re-read: may have just been ratcheted

        if direction == "LONG":
            target_hit = ref_price >= target
            stop_hit   = ref_price <= stop
        else:
            target_hit = ref_price <= target
            stop_hit   = ref_price >= stop

        if target_hit:
            log.info(f"TARGET HIT [{direction}]: {symbol} @ {ref_price:.2f} "
                     f"(ltp={last_price:.2f}, src={ref_source}) (target={target:.2f})")
            if close_fn(rec):
                _verify_exit_fill(dm, rec, target, "TARGET_HIT")
                log_closed_trade(today, rec, exit_price=target, exit_reason="TARGET_HIT", exit_time=now_str)
                changed = True
        elif stop_hit:
            locked_tag = " [profit-locked]" if rec.get("_profit_locked") else ""
            exit_reason = "PROFIT_LOCK_STOP" if rec.get("_profit_locked") else "STOP_HIT"
            log.info(f"STOP HIT [{direction}]: {symbol} @ {ref_price:.2f} "
                     f"(ltp={last_price:.2f}, src={ref_source}) (stop={stop:.2f}){locked_tag}")
            if close_fn(rec):
                _verify_exit_fill(dm, rec, stop, exit_reason)
                log_closed_trade(today, rec, exit_price=stop, exit_reason=exit_reason, exit_time=now_str)
                changed = True
        elif ref_source == "book":
            # The corroboration guard at work: LTP alone would have triggered
            # but the live book disagreed — log visibly (not as a warning,
            # this is the fix doing its job) so it's traceable in review.
            ltp_stop_hit = (last_price <= stop) if direction == "LONG" else (last_price >= stop)
            ltp_target_hit = (last_price >= target) if direction == "LONG" else (last_price <= target)
            if ltp_stop_hit and not stop_hit:
                log.info(f"STOP CHECK  [{direction}]: {symbol} | LTP {last_price:.2f} past stop "
                         f"{stop:.2f} but book price {ref_price:.2f} disagrees — holding position")
            elif ltp_target_hit and not target_hit:
                log.info(f"TARGET CHECK[{direction}]: {symbol} | LTP {last_price:.2f} past target "
                         f"{target:.2f} but book price {ref_price:.2f} disagrees — holding position")

    if changed:
        new_long, new_short, _, _ = state.snapshot()
        save_open_trade(today, new_long, new_short)
    elif lock_updated:
        # persist the ratcheted stop for crash-safety (rec objects were mutated in place)
        save_open_trade(today, long_rec, short_rec)


def _force_time_exit(state: AgentState, dm: LiveDataManager,
                     today: date, exit_time: str) -> None:
    """Force-close all open positions at 3:15 PM."""
    long_rec, short_rec, long_placed, short_placed = state.snapshot()
    if not long_placed and not short_placed:
        log.info("No trade was placed today — no exit needed")
        return

    for rec, close_fn in ((long_rec, state.close_long_if_current), (short_rec, state.close_short_if_current)):
        if rec is None:
            continue
        symbol    = rec["symbol"]
        direction = rec.get("direction", "LONG")
        last_price = dm.get_last_price(symbol)
        if last_price is None:
            last_price = float(rec["signal"]["entry"])
            log.warning(f"  No live price for {symbol} — using entry price as exit")
        log.info(f"TIME EXIT [{direction}]: {symbol} @ {last_price:.2f} (3:15 PM square-off)")
        if close_fn(rec):
            _verify_exit_fill(dm, rec, last_price, "TIME_EXIT")
            log_closed_trade(today, rec, exit_price=last_price, exit_reason="TIME_EXIT", exit_time=exit_time)

    save_open_trade(today, None, None)


def _verify_exit_fill(dm: LiveDataManager, rec: dict, exit_price: float,
                      exit_reason: str) -> None:
    """
    Depth-check the exit the same way entries are checked: can the OPPOSITE side
    of the book actually absorb this close at the booked price? Diagnostic only —
    the paper trade still books at the level (flat slippage is in the cost model);
    this logs whether the exit would really have completed, and stamps the result
    on the rec so it lands in live_paper_trades.csv (exit_fill_status column).
    """
    try:
        fc = check_exit_fill(dm, rec["symbol"], exit_price, int(rec["shares"]),
                             rec.get("direction", "LONG"), exit_reason)
        rec["_exit_fill_status"] = fc["status"]
        level = log.info if fc["status"] == "EXIT_CONFIRMED" else log.warning
        level(f"EXIT FILL   [{rec.get('direction', 'LONG')}]: {rec['symbol']} | {fc['msg']}")
    except Exception as e:
        rec["_exit_fill_status"] = "CHECK_ERROR"
        log.warning(f"EXIT FILL   [{rec.get('direction', 'LONG')}]: {rec['symbol']} | "
                    f"check failed ({e}) — exit UNVERIFIED")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_ist() -> datetime:
    return datetime.now(IST)


def _next_bar_close(now: datetime) -> datetime:
    """
    Return the datetime of the next 5-min bar close.
    NSE bars: 9:15, 9:20, 9:25, ..., 15:25 (labelled by bar open time).
    A bar "closes" when the next bar starts, i.e. at :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55.

    We treat bars as closing at multiples of 5 minutes past the hour.
    """
    minute  = now.minute
    seconds = now.second + now.microsecond / 1e6
    # Minutes until next 5-min boundary
    offset  = 5 - (minute % 5)
    if offset == 5 and seconds < 1:
        offset = 5   # we're exactly on the mark — wait for next bar
    next_dt = now.replace(second=0, microsecond=0) + timedelta(minutes=offset)
    return next_dt


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live Paper Trading Agent — Phase 2.5")
    p.add_argument(
        "--token", metavar="ACCESS_TOKEN",
        help="Broker access token for today"
    )
    p.add_argument(
        "--broker", default="zerodha",
        help="Broker to use: zerodha (default) or groww"
    )
    p.add_argument(
        "--wf-window", type=int, default=5, metavar="N",
        help="Walk-forward window whose frozen weights to use (default: 5 → wf5_weights.json)"
    )
    return p.parse_args()


def _load_weights(wf_window: int = 5) -> dict:
    """Load frozen WF weights. Never loads strategy_weights.json (adaptive training file)."""
    frozen = WEIGHTS_FILE.parent / f"wf{wf_window}_weights.json"
    if frozen.exists():
        with open(frozen) as f:
            return json.load(f)
    log.warning(f"wf{wf_window}_weights.json not found — falling back to strategy_weights.json")
    if WEIGHTS_FILE.exists():
        with open(WEIGHTS_FILE) as f:
            return json.load(f)
    log.warning("No weights file found — using uniform weights (1.0 per strategy)")
    return {}


def _load_universe_symbols() -> list[str]:
    """Load tradingsymbols from config/universe.csv."""
    from config.settings import UNIVERSE_FILE
    import pandas as pd
    if not UNIVERSE_FILE.exists():
        log.warning("universe.csv not found — will scan all stocks with parquet data")
        return []
    df = pd.read_csv(UNIVERSE_FILE)
    col = "tradingsymbol" if "tradingsymbol" in df.columns else df.columns[0]
    return df[col].tolist()


def _load_history_for_symbols(symbols: list[str], today: date) -> dict:
    """Load parquet history for all symbols. Logs progress every 100 stocks."""
    import pandas as pd
    from config.settings import STOCKS_DIR

    result   = {}
    curr_yr  = today.year
    prev_yr  = curr_yr - 1
    total    = len(symbols)

    for i, symbol in enumerate(symbols):
        if i > 0 and i % 100 == 0:
            log.info(f"  Loading history... {i}/{total} stocks done")

        dfs = []
        for yr in [prev_yr, curr_yr]:
            path = STOCKS_DIR / str(yr) / f"{symbol}.parquet"
            if path.exists():
                try:
                    df = pd.read_parquet(path)
                    df["datetime"] = _to_ist(df["datetime"])
                    dfs.append(df)
                except Exception:
                    pass
        if dfs:
            combined = (pd.concat(dfs)
                        .drop_duplicates("datetime")
                        .sort_values("datetime")
                        .reset_index(drop=True))
            history = combined[combined["datetime"].dt.date < today]
            if not history.empty:
                result[symbol] = history.reset_index(drop=True)

    return result


def _backfill_today_bars(kite, dm: LiveDataManager, today: date) -> None:
    """
    Fetch today's completed 5-min bars from Kite historical API and seed the
    candle builders.  Called when the agent starts AFTER market open with no
    checkpoint data (late start or first-ever run mid-day).

    Without this, strategies only see bars captured since the agent started —
    missing all price action from 9:15 AM up to the actual start time.
    """
    now_ist = _now_ist()

    # Last fully-closed bar open time  (e.g. at 12:03 PM → last closed bar = 11:55)
    m = now_ist.minute
    last_closed = now_ist.replace(minute=m - (m % 5), second=0, microsecond=0) - timedelta(minutes=5)
    from_dt = now_ist.replace(hour=9, minute=15, second=0, microsecond=0).replace(tzinfo=None)
    to_dt   = last_closed.replace(tzinfo=None)

    if to_dt < from_dt:
        log.info("Late-start backfill: market not open long enough yet — skipping")
        return

    log.info(f"Late-start backfill: fetching today's bars 09:15 → {to_dt.strftime('%H:%M')} from Kite API...")

    def _fetch(token: int) -> list[dict]:
        bars = kite.historical_data(
            instrument_token=token,
            from_date=from_dt,
            to_date=to_dt,
            interval="5minute",
            continuous=False,
            oi=False,
        )
        result = []
        for b in bars:
            dt = b["date"]
            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            result.append({
                "datetime": dt,
                "open":   float(b["open"]),
                "high":   float(b["high"]),
                "low":    float(b["low"]),
                "close":  float(b["close"]),
                "volume": int(b["volume"]),
            })
        return result

    filled = 0
    for i, symbol in enumerate(dm.symbols):
        token = dm._imap.get(symbol)
        if not token:
            continue
        try:
            bars = _fetch(token)
            if bars:
                dm._builders[symbol].seed(bars)
                filled += 1
        except Exception as e:
            log.debug(f"  {symbol}: backfill failed — {e}")
        # Kite allows 3 historical requests/sec
        if (i + 1) % 3 == 0:
            time_mod.sleep(1.0)

    # Backfill Nifty too (needed by REL-STR strategy)
    try:
        nifty_bars = _fetch(NIFTY50_TOKEN)
        if nifty_bars:
            dm._nifty_builder.seed(nifty_bars)
    except Exception as e:
        log.debug(f"  NIFTY50: backfill failed — {e}")

    log.info(f"Late-start backfill complete: {filled}/{len(dm.symbols)} symbols, "
             f"{len(bars) if filled else 0} bars each")


def _print_summary(state: AgentState, today: date) -> None:
    long_rec, short_rec, long_placed, short_placed = state.snapshot()
    log.info("")
    log.info("=" * 65)
    log.info(f"  Day summary — {today}")
    if not long_placed and not short_placed:
        log.info("  No trade placed today (no signal passed all filters)")
    for rec, placed, still_open, label in (
        (long_rec,  long_placed,  state.is_long_open(),  "LONG"),
        (short_rec, short_placed, state.is_short_open(), "SHORT"),
    ):
        if not placed:
            continue
        if rec is None:
            log.info(f"  [{label}] trade placed and closed — see live_paper_trades.csv")
            continue
        sig = rec["signal"]
        log.info(f"  [{label}] {rec['symbol']} | driver={sig['strategy']} "
                 f"agreeing={rec['agreeing']} score={rec['score']:.2f}")
        log.info(f"    entry={sig['entry']:.2f}  target={sig['target']:.2f}  "
                 f"stop={sig['stop']:.2f}  size=Rs {rec['position_rs']:,.0f} [{rec['conviction_tier']}]")
        if still_open:
            log.info(f"    WARNING: position not closed — check live_open_trade.json")
        else:
            log.info(f"    Exit recorded — see live_paper_trades.csv")
    log.info("=" * 65)

    # EOD risk check — writes halt flags if daily/monthly limits breached
    write_eod_risk_check(today)


def _fill_parquet_gaps(kite, imap: dict, today: date) -> None:
    """
    Check all universe stocks for missing parquet dates and download them.
    Called at startup after instrument map is loaded, before history loads.
    Uses the active broker (Zerodha or Groww) so no cross-broker dependency.
    Returns immediately if all parquets are up to date (typical case).
    """
    from data_pipeline.downloader import fill_gaps
    try:
        result = fill_gaps(kite, imap, today)
        if result["filled"] > 0:
            log.info(
                f"Gap-fill complete: {result['filled']} stocks updated"
                + (f", {len(result['failed'])} failed — {result['failed']}" if result["failed"] else "")
            )
    except Exception as e:
        log.warning(f"Gap-fill failed (non-fatal): {e}")


def _run_eod_download(kite, imap: dict, today: date) -> None:
    """
    Download today's 5-min bars for all 500 universe stocks after market close.
    Waits until 15:31 IST if called early (e.g. manual stop before close).
    imap is passed to download_eod so Groww exchange_tokens are used when
    running with --broker groww (no dependency on Zerodha tokens from universe.csv).
    """
    from data_pipeline.downloader import download_eod

    # Wait until 15:31 so API has the full day's candles available
    now_ist = _now_ist()
    target  = now_ist.replace(hour=15, minute=31, second=0, microsecond=0)
    wait_s  = (target - now_ist).total_seconds()
    if wait_s > 0:
        log.info(f"EOD download: waiting {int(wait_s)}s until 15:31 for API data to settle...")
        time_mod.sleep(wait_s)

    log.info("=" * 65)
    log.info("  Starting EOD data download for tomorrow's session")
    log.info("=" * 65)
    try:
        result = download_eod(kite, today, imap=imap)
        log.info(
            f"  EOD download done — {result['completed']} stocks saved, "
            f"{result['failed']} failed. Parquet files updated for {today}."
        )
        log.info("  Tomorrow's agent will load today's bars as history automatically.")
    except Exception as e:
        log.error(f"  EOD download failed: {e}")
        log.error("  Run manually: python -c \"from data_pipeline.downloader import download_eod; ...\"")
    log.info("=" * 65)


if __name__ == "__main__":
    main()

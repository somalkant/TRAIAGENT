"""
Groww broker integration.

Authentication:
    GROWW_API_TOKEN + TOTP_TOKEN_SECRET → daily GROWW_ACCESS_TOKEN
    Managed by live/groww_auth.py (auto-refresh via TOTP, no copy-paste needed).

Adapters:
    GrowwClientAdapter  — wraps GrowwAPI with a KiteConnect-compatible interface
    GrowwTickerAdapter  — polls GrowwAPI.get_ltp() every 1s, delivers
                          KiteTicker-compatible ticks to the live agent

Note on tokens:
    Kite uses numeric instrument_token values for WebSocket subscriptions.
    Groww uses integer exchange_token for the same purpose.
    We use int(exchange_token) from Groww's instrument CSV as our token so the
    mapping is consistent across instrument_map → data_manager → ticker.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from brokers.base import BaseBroker

log = logging.getLogger(__name__)

_CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints"

# The live agent's data_manager routes ticks with this exact token value to the
# Nifty50 candle builder. We keep it here so Groww ticks for Nifty are tagged
# with the same integer and the routing works unchanged.
_NIFTY50_TOKEN     = 256265
# Groww uses "NSE_NIFTY 50" as the exchange+symbol key for the index
_NIFTY_GROWW_KEY   = "NSE_NIFTY 50"
# Nifty50 groww_symbol (used by get_historical_candles)
_NIFTY_GROWW_SYM   = "NSE_NIFTY 50"


# ─────────────────────────────────────────────────────────────────────────────
# KiteConnect-compatible client adapter
# ─────────────────────────────────────────────────────────────────────────────

class GrowwClientAdapter:
    """
    Wraps GrowwAPI to expose the KiteConnect interface expected by live/agent.py.

    Methods used by the agent:
      instruments(exchange)                              → instrument list
      set_access_token(token)                            → authenticate
      historical_data(token, from_date, to_date, ...)   → OHLCV candles
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key  = api_key
        self._client   = None
        # Populated by instruments() — needed for historical_data() lookups
        self._token_to_symbol:    dict[int, str] = {}
        self._token_to_groww_sym: dict[int, str] = {}  # {token: groww_symbol}

    def set_access_token(self, token: str) -> None:
        from growwapi import GrowwAPI
        self._client = GrowwAPI(token)

    def instruments(self, exchange: str = "NSE") -> list[dict]:
        """Return NSE equity instruments in Kite-compatible format."""
        df = self._client.get_all_instruments()

        # Groww instrument CSV uses "trading_symbol" (with underscore)
        # and "segment" = "CASH" for equities.
        df_eq = df[(df["exchange"] == exchange) & (df["segment"] == "CASH")]

        result = []
        for _, row in df_eq.iterrows():
            try:
                token    = int(row["exchange_token"])
                sym      = str(row["trading_symbol"])
                groww_sym = str(row.get("groww_symbol", f"{exchange}_{sym}"))
                self._token_to_symbol[token]    = sym
                self._token_to_groww_sym[token] = groww_sym
                result.append({
                    "tradingsymbol":    sym,
                    "instrument_token": token,
                    "instrument_type":  "EQ",
                })
            except (ValueError, KeyError, TypeError):
                pass

        log.info(f"Groww instruments: {len(result)} NSE equities")
        return result

    def historical_data(
        self,
        instrument_token: int,
        from_date,
        to_date,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict]:
        """Return OHLCV candles in Kite-compatible format."""
        from growwapi import GrowwAPI

        # Special case: Nifty50 index
        if instrument_token == _NIFTY50_TOKEN:
            groww_sym = _NIFTY_GROWW_SYM
        else:
            groww_sym = self._token_to_groww_sym.get(instrument_token)
            if not groww_sym:
                return []

        from datetime import date as _date, datetime as _datetime
        fmt       = "%Y-%m-%d %H:%M:%S"
        if isinstance(from_date, _datetime):
            start_str = from_date.strftime(fmt)
        elif isinstance(from_date, _date):
            start_str = from_date.strftime("%Y-%m-%d 00:00:00")
        else:
            start_str = str(from_date)
        if isinstance(to_date, _datetime):
            end_str = to_date.strftime(fmt)
        elif isinstance(to_date, _date):
            # Use end-of-day so all intraday candles (09:15–15:30) are included
            end_str = to_date.strftime("%Y-%m-%d 23:59:59")
        else:
            end_str = str(to_date)

        _interval_map = {
            "minute":   GrowwAPI.CANDLE_INTERVAL_MIN_1,
            "3minute":  GrowwAPI.CANDLE_INTERVAL_MIN_3,
            "5minute":  GrowwAPI.CANDLE_INTERVAL_MIN_5,
            "10minute": GrowwAPI.CANDLE_INTERVAL_MIN_10,
            "15minute": GrowwAPI.CANDLE_INTERVAL_MIN_15,
            "30minute": GrowwAPI.CANDLE_INTERVAL_MIN_30,
            "60minute": GrowwAPI.CANDLE_INTERVAL_HOUR_1,
            "day":      GrowwAPI.CANDLE_INTERVAL_DAY,
        }
        groww_interval = _interval_map.get(interval, GrowwAPI.CANDLE_INTERVAL_MIN_5)

        try:
            resp    = self._client.get_historical_candles(
                exchange="NSE",
                segment="CASH",
                groww_symbol=groww_sym,
                start_time=start_str,
                end_time=end_str,
                candle_interval=groww_interval,
            )
            # Response: {"candles": [[ts, o, h, l, c, v], …], …} — candles as arrays
            candles = resp.get("candles", []) if isinstance(resp, dict) else []
            result  = []
            for c in candles:
                try:
                    if isinstance(c, dict):
                        # Dict format: {"timestamp":…, "open":…, "high":…, …}
                        raw_dt = c.get("timestamp") or c.get("date") or c.get("time") or ""
                        o, h, l, cl, vol = (float(c.get("open", 0)), float(c.get("high", 0)),
                                            float(c.get("low", 0)), float(c.get("close", 0)),
                                            int(c.get("volume", 0)))
                    elif isinstance(c, (list, tuple)) and len(c) >= 5:
                        # Array format: [timestamp, open, high, low, close, volume]
                        raw_dt = c[0]
                        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                        vol = int(c[5]) if len(c) > 5 else 0
                    else:
                        continue

                    if isinstance(raw_dt, str) and raw_dt:
                        try:
                            dt = datetime.strptime(raw_dt[:19], "%Y-%m-%dT%H:%M:%S")
                        except ValueError:
                            dt = datetime.strptime(raw_dt[:19], "%Y-%m-%d %H:%M:%S")
                    elif isinstance(raw_dt, (int, float)):
                        dt = datetime.fromtimestamp(raw_dt / 1000)
                    else:
                        continue

                    result.append({"date": dt, "open": o, "high": h, "low": l, "close": cl, "volume": vol})
                except Exception:
                    continue
            return result
        except Exception as e:
            sym_label = self._token_to_symbol.get(instrument_token, str(instrument_token))
            log.warning(f"historical_data({sym_label} {start_str}→{end_str}): {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# NATS log-spam suppression
# ─────────────────────────────────────────────────────────────────────────────

class _NatsLogFilter(logging.Filter):
    """
    Rate-limits growwapi's NATS client logging during connection outages.

    When the Groww NATS WebSocket drops, nats-py auto-reconnects with the
    original (now stale) subscription token, the server rejects it ("empty
    response from server when expecting INFO message"), and every failed retry
    logs "Error: <often empty>" — one line every ~4 seconds until the client
    gives up. The outage itself is real (the feed watchdog below handles
    recovery); the spam is not useful, so:

      - empty "Error: " lines are dropped entirely
      - identical messages repeat at most once per 60s, with a suppressed-count
      - the first occurrence of any message always passes through
    """

    _WINDOW_SECS = 60.0

    def __init__(self):
        super().__init__()
        self._last_emit: dict[str, float] = {}   # msg -> last emit monotonic ts
        self._suppressed: dict[str, int] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage().strip()
        if msg in ("Error:", "Error: "):          # empty reconnect-failure error
            return False
        now = time.monotonic()
        last = self._last_emit.get(msg)
        if last is not None and (now - last) < self._WINDOW_SECS:
            self._suppressed[msg] = self._suppressed.get(msg, 0) + 1
            return False
        n = self._suppressed.pop(msg, 0)
        if n:
            record.msg = f"{record.msg}  (+{n} repeats suppressed in last {int(self._WINDOW_SECS)}s)"
            record.args = None
        self._last_emit[msg] = now
        return True


def _install_nats_log_filter() -> None:
    """Attach the rate-limit filter to growwapi's NATS client logger (idempotent)."""
    nats_logger = logging.getLogger("growwapi.groww.nats_client")
    if not any(isinstance(f, _NatsLogFilter) for f in nats_logger.filters):
        nats_logger.addFilter(_NatsLogFilter())


# ─────────────────────────────────────────────────────────────────────────────
# KiteTicker-compatible polling ticker
# ─────────────────────────────────────────────────────────────────────────────

class GrowwTickerAdapter:
    """
    KiteTicker-compatible ticker for Groww.

    Primary:  GrowwFeed (NATS WebSocket) — real-time push ticks per price change.
    Nifty50:  REST-polled every 2 s (index not subscribable via GrowwFeed equity API).
    Fallback: REST polling in 50-symbol batches if GrowwFeed NATS connection fails.

    Proto fields from StocksLivePriceProto: ltp, volume, open, high, low, close,
    tsInMillis, avgPrice, bidQty, offerQty, highPriceRange, lowPriceRange.
    """

    MODE_FULL   = "full"
    MODE_QUOTE  = "quote"
    MODE_LTP    = "ltp"

    _BATCH_SIZE      = 50    # REST fallback: Groww get_ltp silently drops beyond this
    _NIFTY_POLL_SECS = 2.0   # Nifty index REST polling interval

    _WATCHDOG_SILENCE_SECS = 60    # rebuild feed if no stock tick for this long in market hours
    _WATCHDOG_POLL_SECS    = 10
    _REBUILD_COOLDOWN_SECS = 30    # min gap between rebuild attempts

    def __init__(self, api_key: str, access_token: str):
        from growwapi import GrowwAPI
        _install_nats_log_filter()
        self._client           = GrowwAPI(access_token)
        self._subscribed       : list[int]                    = []
        self._token_to_groww   : dict[int, str]               = {}  # {token: "NSE_SYMBOL"}
        self._groww_to_token   : dict[str, int]               = {}  # {"NSE_SYMBOL": token}
        self._running          : bool                         = False
        self._feed                                            = None  # GrowwFeed instance
        self._nifty_thread     : Optional[threading.Thread]  = None
        self._fallback_thread  : Optional[threading.Thread]  = None
        self._watchdog_thread  : Optional[threading.Thread]  = None
        self._last_stock_tick  : float                        = time.monotonic()
        self._last_rebuild     : float                        = 0.0
        self._rebuild_lock                                    = threading.Lock()

        self.on_connect = None
        self.on_ticks   = None
        self.on_depth   = None   # callback(ws, [{instrument_token, buy_levels, sell_levels}])
        self.on_close   = None
        self.on_error   = None

    # ── KiteTicker interface ──────────────────────────────────────────────────

    def subscribe(self, tokens: list[int]) -> None:
        self._subscribed = list(tokens)
        self._build_groww_map()

    def set_mode(self, mode, tokens) -> None:
        pass

    def connect(self, threaded: bool = True) -> None:
        self._running = True
        # Fire on_connect FIRST — live agent calls subscribe() inside this callback,
        # which populates self._subscribed and self._token_to_groww before feed starts.
        if self.on_connect:
            try:
                self.on_connect(self, {})
            except Exception as e:
                log.error(f"on_connect callback error: {e}")

        # Token maps are now ready — start real-time feed (or REST fallback)
        try:
            self._start_feed()
            log.info("GrowwTickerAdapter: GrowwFeed WebSocket active (real-time ticks)")
        except Exception as e:
            log.warning(f"GrowwFeed unavailable ({e}) — falling back to REST polling")
            self._fallback_thread = threading.Thread(
                target=self._poll_loop, daemon=True, name="groww-rest-poll"
            )
            self._fallback_thread.start()

    def close(self) -> None:
        self._running = False
        if self._feed is not None:
            try:
                instrument_list = [
                    {"exchange": "NSE", "segment": "CASH", "exchange_token": str(t)}
                    for t in self._subscribed
                    if t != _NIFTY50_TOKEN and t in self._token_to_groww
                ]
                if instrument_list:
                    self._feed.unsubscribe_ltp(instrument_list)
                    self._feed.unsubscribe_market_depth(instrument_list)
            except Exception:
                pass
        if self.on_close:
            try:
                self.on_close(self, 0, "closed")
            except Exception:
                pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_groww_map(self) -> None:
        """Build {token → "NSE_SYMBOL"} from the instruments.json cache."""
        cache = _CHECKPOINT_DIR / "instruments.json"
        if not cache.exists():
            log.warning("instruments.json not found — Groww ticker map will be empty")
            return
        try:
            data = json.loads(cache.read_text())
            imap = data.get("map", {})            # {"SYMBOL": token}
            rev  = {v: k for k, v in imap.items()}   # {token: "SYMBOL"}
            for token in self._subscribed:
                if token == _NIFTY50_TOKEN:
                    continue
                sym = rev.get(token)
                if sym:
                    groww_key = f"NSE_{sym}"
                    self._token_to_groww[token] = groww_key
                    self._groww_to_token[groww_key] = token
            log.info(f"Groww ticker map built: {len(self._token_to_groww)} stocks")
        except Exception as e:
            log.warning(f"Failed to build Groww ticker map: {e}")

    def _start_feed(self) -> None:
        """Connect GrowwFeed (NATS WebSocket) and subscribe to all stock tokens."""
        from growwapi.groww.feed import GrowwFeed

        stock_tokens = [
            t for t in self._subscribed
            if t != _NIFTY50_TOKEN and t in self._token_to_groww
        ]
        has_nifty = _NIFTY50_TOKEN in self._subscribed

        if not stock_tokens:
            raise ValueError("No mapped stock tokens to subscribe via GrowwFeed")

        instrument_list = [
            {"exchange": "NSE", "segment": "CASH", "exchange_token": str(t)}
            for t in stock_tokens
        ]

        log.info(f"GrowwFeed: connecting NATS WebSocket for {len(instrument_list)} stocks...")
        self._feed = GrowwFeed(self._client)
        self._feed.subscribe_ltp(instrument_list, on_data_received=self._on_feed_tick)
        self._feed.subscribe_market_depth(instrument_list, on_data_received=self._on_depth_tick)
        self._last_stock_tick = time.monotonic()   # fresh silence window for the new feed
        log.info(f"GrowwFeed: subscribed LTP + market depth for {len(instrument_list)} NSE equities")

        if has_nifty and (self._nifty_thread is None or not self._nifty_thread.is_alive()):
            self._nifty_thread = threading.Thread(
                target=self._nifty_poll_loop, daemon=True, name="groww-nifty-poll"
            )
            self._nifty_thread.start()
            log.info("GrowwFeed: Nifty50 via REST poll (2 s interval)")

        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop, daemon=True, name="groww-feed-watchdog"
            )
            self._watchdog_thread.start()
            log.info(f"GrowwFeed: watchdog active (rebuild after "
                     f"{self._WATCHDOG_SILENCE_SECS}s tick silence)")

    def _watchdog_loop(self) -> None:
        """
        Rebuild the NATS feed after a sustained tick outage.

        nats-py's built-in reconnect retries with the ORIGINAL subscription token,
        which the Groww server rejects once it has expired ("empty response from
        server when expecting INFO message") — so a dropped connection can never
        recover by itself. The only reliable recovery is a full rebuild: fresh
        GrowwFeed, fresh token, fresh subscriptions. Before this watchdog, the
        agent's 300s bar-level staleness sweep was the only rescue, leaving open
        positions blind to exits for up to 5+ minutes (observed: 425s).
        """
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        from datetime import time as dtime

        while self._running:
            time.sleep(self._WATCHDOG_POLL_SECS)
            if not self._running:
                return
            now_t = datetime.now(ist).time()
            if not (dtime(9, 15) <= now_t <= dtime(15, 30)):
                continue   # no ticks outside market hours is normal
            silence = time.monotonic() - self._last_stock_tick
            if silence < self._WATCHDOG_SILENCE_SECS:
                continue
            if time.monotonic() - self._last_rebuild < self._REBUILD_COOLDOWN_SECS:
                continue
            with self._rebuild_lock:
                self._last_rebuild = time.monotonic()
                log.warning(f"GrowwFeed watchdog: no stock ticks for {silence:.0f}s — "
                            f"rebuilding feed with a fresh subscription...")
                old_feed = self._feed
                try:
                    self._start_feed()
                    log.info("GrowwFeed watchdog: feed rebuilt successfully")
                except Exception as e:
                    log.error(f"GrowwFeed watchdog: rebuild failed ({e}) — retrying in "
                              f"{self._REBUILD_COOLDOWN_SECS}s")
                    continue
                if old_feed is not None:
                    try:
                        instrument_list = [
                            {"exchange": "NSE", "segment": "CASH", "exchange_token": str(t)}
                            for t in self._subscribed
                            if t != _NIFTY50_TOKEN and t in self._token_to_groww
                        ]
                        old_feed.unsubscribe_ltp(instrument_list)
                        old_feed.unsubscribe_market_depth(instrument_list)
                    except Exception:
                        pass   # old connection is already dead — best-effort cleanup

    def _on_feed_tick(self, meta: dict) -> None:
        """
        Called by GrowwFeed on each LTP update (one instrument per call).
        meta = {"exchange": "NSE", "segment": "CASH", "feed_key": "<exchange_token>", ...}
        Proto fields available: ltp, volume, open, high, low, close, tsInMillis, avgPrice.
        """
        if not self._running:
            return
        self._last_stock_tick = time.monotonic()   # feed-watchdog heartbeat
        try:
            token_str = str(meta.get("feed_key", ""))
            if not token_str.isdigit():
                return
            int_token = int(token_str)

            exchange  = meta.get("exchange", "NSE")
            segment   = meta.get("segment",  "CASH")
            all_ltp   = self._feed.get_ltp()
            tick_data = all_ltp.get(exchange, {}).get(segment, {}).get(token_str, {})

            ltp       = float(tick_data.get("ltp")      or 0)
            vol       = int(tick_data.get("volume")    or 0)
            bid_qty   = int(tick_data.get("bidQty")    or 0)
            offer_qty = int(tick_data.get("offerQty")  or 0)

            if ltp > 0 and self.on_ticks:
                self.on_ticks(self, [{
                    "instrument_token": int_token,
                    "last_price":       ltp,
                    "volume_traded":    vol,
                    "bid_qty":          bid_qty,
                    "offer_qty":        offer_qty,
                }])
        except Exception as e:
            log.debug(f"GrowwFeed tick parse error: {e}")

    def _on_depth_tick(self, meta: dict) -> None:
        """
        Called by GrowwFeed on each market-depth update (StocksMarketDepthProto).
        Parses buyBook / sellBook into sorted price-level lists and fires on_depth.
        """
        if not self._running or not self.on_depth:
            return
        try:
            token_str = str(meta.get("feed_key", ""))
            if not token_str.isdigit():
                return
            int_token = int(token_str)

            exchange  = meta.get("exchange", "NSE")
            segment   = meta.get("segment",  "CASH")
            all_depth = self._feed.get_market_depth()
            depth_data = all_depth.get(exchange, {}).get(segment, {}).get(token_str, {})

            if not depth_data:
                return

            def _parse_book(book: dict) -> list[dict]:
                levels = []
                for v in book.values():
                    if isinstance(v, dict):
                        p = float(v.get("price") or 0)
                        q = float(v.get("qty")   or 0)
                        if p > 0:
                            levels.append({"price": p, "qty": q})
                return levels

            buy_levels  = sorted(_parse_book(depth_data.get("buyBook",  {})),
                                 key=lambda x: x["price"], reverse=True)  # best bid first
            sell_levels = sorted(_parse_book(depth_data.get("sellBook", {})),
                                 key=lambda x: x["price"])                 # best ask first

            self.on_depth(self, [{
                "instrument_token": int_token,
                "buy_levels":       buy_levels,
                "sell_levels":      sell_levels,
            }])
        except Exception as e:
            log.debug(f"GrowwFeed depth parse error: {e}")

    def _nifty_poll_loop(self) -> None:
        """Poll Nifty50 index LTP via REST every 2 s (index not in GrowwFeed equity sub)."""
        while self._running:
            try:
                resp = self._client.get_ltp((_NIFTY_GROWW_KEY,), "CASH")
                data = resp.get(_NIFTY_GROWW_KEY, 0)
                nltp, _ = _parse_ltp_response(data)
                if nltp > 0 and self.on_ticks:
                    self.on_ticks(self, [{
                        "instrument_token": _NIFTY50_TOKEN,
                        "last_price":       nltp,
                        "volume_traded":    0,
                    }])
            except Exception as e:
                log.debug(f"Nifty REST poll error: {e}")
            time.sleep(self._NIFTY_POLL_SECS)

    # ── REST polling fallback (used when GrowwFeed NATS connection fails) ─────

    def _poll_loop(self) -> None:
        """REST polling fallback — 50-symbol batches every 1 s."""
        stock_tokens = [t for t in self._subscribed if t != _NIFTY50_TOKEN]
        has_nifty    = _NIFTY50_TOKEN in self._subscribed

        while self._running:
            try:
                ticks = []
                groww_keys = [
                    self._token_to_groww[t]
                    for t in stock_tokens
                    if t in self._token_to_groww
                ]
                for i in range(0, len(groww_keys), self._BATCH_SIZE):
                    chunk = groww_keys[i : i + self._BATCH_SIZE]
                    resp  = self._client.get_ltp(tuple(chunk), "CASH")
                    for groww_key, data in resp.items():
                        token = self._groww_to_token.get(groww_key)
                        if token is None:
                            continue
                        ltp, vol = _parse_ltp_response(data)
                        if ltp > 0:
                            ticks.append({
                                "instrument_token": token,
                                "last_price":       ltp,
                                "volume_traded":    vol,
                            })

                if has_nifty:
                    try:
                        nresp = self._client.get_ltp((_NIFTY_GROWW_KEY,), "CASH")
                        ndata = nresp.get(_NIFTY_GROWW_KEY, 0)
                        nltp, _ = _parse_ltp_response(ndata)
                        if nltp > 0:
                            ticks.append({
                                "instrument_token": _NIFTY50_TOKEN,
                                "last_price":       nltp,
                                "volume_traded":    0,
                            })
                    except Exception:
                        pass

                if ticks and self.on_ticks:
                    self.on_ticks(self, ticks)

            except Exception as e:
                if self.on_error:
                    try:
                        self.on_error(self, 0, str(e))
                    except Exception:
                        pass
                log.warning(f"GrowwTickerAdapter REST poll error: {e}")

            time.sleep(1.0)


def _parse_ltp_response(data) -> tuple[float, int]:
    """Extract (ltp, volume) from a Groww get_ltp response entry."""
    if isinstance(data, dict):
        ltp = float(data.get("ltp") or data.get("last_price") or data.get("lastPrice") or 0)
        vol = int(data.get("volume") or data.get("volume_traded") or data.get("totalTradedVolume") or 0)
    elif isinstance(data, (int, float)):
        ltp = float(data)
        vol = 0
    else:
        ltp, vol = 0.0, 0
    return ltp, vol


# ─────────────────────────────────────────────────────────────────────────────
# Broker class
# ─────────────────────────────────────────────────────────────────────────────

class GrowwBroker(BaseBroker):
    """Groww broker — full implementation using growwapi SDK + TOTP auth."""

    @property
    def name(self) -> str:
        return "groww"

    @property
    def display_name(self) -> str:
        return "Groww"

    def authenticate(self, log) -> str:
        """
        Auto-refresh access token using TOTP — no copy-paste required.
        Reads GROWW_API_TOKEN and TOTP_TOKEN_SECRET from .env.
        """
        from live.groww_auth import (
            _load_env, _is_token_valid, _fetch_new_token, _save_token_to_env
        )
        import base64

        api_token, totp_secret, cached_token = _load_env()

        if _is_token_valid(cached_token):
            try:
                exp = json.loads(
                    base64.urlsafe_b64decode(
                        cached_token.split(".")[1] + "=="
                    )
                ).get("exp", 0)
                log.info(
                    f"Groww token valid — expires "
                    f"{datetime.fromtimestamp(exp).strftime('%H:%M')}"
                )
            except Exception:
                pass
            token = cached_token
        else:
            log.info("Refreshing Groww access token via TOTP...")
            token = _fetch_new_token(api_token, totp_secret)
            _save_token_to_env(token)
            log.info("Groww access token refreshed and saved to .env")

        # Cache for crash-restart recovery
        _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        (_CHECKPOINT_DIR / "access_token.json").write_text(
            json.dumps({"access_token": token, "date": str(date.today()), "broker": "groww"})
        )
        return token

    def get_credentials(self, args) -> tuple[str, str]:
        """Returns (GROWW_API_TOKEN, GROWW_ACCESS_TOKEN)."""
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")

        api_token = os.getenv("GROWW_API_TOKEN", "")
        if not api_token:
            raise RuntimeError("GROWW_API_TOKEN missing in .env")

        access_token = getattr(args, "token", None) or os.getenv("GROWW_ACCESS_TOKEN", "")
        if not access_token:
            raise RuntimeError(
                "GROWW_ACCESS_TOKEN not found. Run python run_live.py to authenticate."
            )
        return api_token, access_token

    def get_api_classes(self) -> tuple[type, type]:
        try:
            import growwapi  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "growwapi not installed. Run: pip install growwapi"
            )
        return GrowwClientAdapter, GrowwTickerAdapter

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

    def __init__(self, api_key: str, access_token: str):
        from growwapi import GrowwAPI
        self._client           = GrowwAPI(access_token)
        self._subscribed       : list[int]                    = []
        self._token_to_groww   : dict[int, str]               = {}  # {token: "NSE_SYMBOL"}
        self._groww_to_token   : dict[str, int]               = {}  # {"NSE_SYMBOL": token}
        self._running          : bool                         = False
        self._feed                                            = None  # GrowwFeed instance
        self._nifty_thread     : Optional[threading.Thread]  = None
        self._fallback_thread  : Optional[threading.Thread]  = None

        self.on_connect = None
        self.on_ticks   = None
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
        log.info(f"GrowwFeed: subscribed to {len(instrument_list)} NSE equities")

        if has_nifty:
            self._nifty_thread = threading.Thread(
                target=self._nifty_poll_loop, daemon=True, name="groww-nifty-poll"
            )
            self._nifty_thread.start()
            log.info("GrowwFeed: Nifty50 via REST poll (2 s interval)")

    def _on_feed_tick(self, meta: dict) -> None:
        """
        Called by GrowwFeed on each LTP update (one instrument per call).
        meta = {"exchange": "NSE", "segment": "CASH", "feed_key": "<exchange_token>", ...}
        Proto fields available: ltp, volume, open, high, low, close, tsInMillis, avgPrice.
        """
        if not self._running:
            return
        try:
            token_str = str(meta.get("feed_key", ""))
            if not token_str.isdigit():
                return
            int_token = int(token_str)

            exchange  = meta.get("exchange", "NSE")
            segment   = meta.get("segment",  "CASH")
            all_ltp   = self._feed.get_ltp()
            tick_data = all_ltp.get(exchange, {}).get(segment, {}).get(token_str, {})

            ltp = float(tick_data.get("ltp")    or 0)
            vol = int(tick_data.get("volume")   or 0)

            if ltp > 0 and self.on_ticks:
                self.on_ticks(self, [{
                    "instrument_token": int_token,
                    "last_price":       ltp,
                    "volume_traded":    vol,
                }])
        except Exception as e:
            log.debug(f"GrowwFeed tick parse error: {e}")

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

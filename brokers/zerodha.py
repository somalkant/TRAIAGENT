"""
Zerodha Kite Connect broker implementation.

Env vars required (.env):
  KITE_API_KEY     — from https://developers.kite.trade/
  KITE_API_SECRET  — from https://developers.kite.trade/

Authentication flow:
  run_live.py calls authenticate() → opens browser URL → user pastes request_token
  → exchanges for access_token → caches in checkpoints/access_token.json (daily).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

from brokers.base import BaseBroker

log = logging.getLogger(__name__)

_CHECKPOINT = Path(__file__).parent.parent / "checkpoints" / "access_token.json"


# ─────────────────────────────────────────────────────────────────────────────
# On-demand quote → shared depth shape (parity with GrowwTickerAdapter.fetch_quote)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_kite_quote(entry: dict | None) -> dict | None:
    """
    Normalize one kiteconnect ``quote()`` entry into the shared depth shape that
    live/data_manager consumes:

        {"last_price": float|None,
         "buy":  [{"price": float, "qty": float}, ...],   # best-bid-first
         "sell": [{"price": float, "qty": float}, ...]}   # best-ask-first

    Kite already returns the 5 depth levels ordered (buy high→low, sell low→high);
    we re-sort defensively anyway. Returns None on any missing/empty book so the
    caller falls back to the LTP rather than acting on bad data — this is the exact
    contract GrowwTickerAdapter.fetch_quote honours, so the exit path behaves
    identically regardless of broker.
    """
    if not isinstance(entry, dict):
        return None
    depth = entry.get("depth") or {}

    def _levels(side: str) -> list[dict]:
        out = []
        for lvl in (depth.get(side) or []):
            if not isinstance(lvl, dict):
                continue
            try:
                p   = float(lvl.get("price") or 0)
                qty = float(lvl.get("quantity") or lvl.get("qty") or 0)
            except (TypeError, ValueError):
                continue
            if p > 0:
                out.append({"price": p, "qty": qty})
        return out

    buy  = sorted(_levels("buy"),  key=lambda x: x["price"], reverse=True)
    sell = sorted(_levels("sell"), key=lambda x: x["price"])
    ltp  = entry.get("last_price")
    if not buy and not sell and not ltp:
        return None
    return {
        "last_price": float(ltp) if ltp else None,
        "buy":  buy,
        "sell": sell,
    }


def _make_kite_ticker_adapter(kite_ticker_cls, kite_connect_cls):
    """
    Build a KiteTicker subclass that adds the broker-agnostic ``fetch_quote`` hook
    (on-demand REST depth refresh — parity with GrowwTickerAdapter). Returned by a
    factory so ``kiteconnect`` is imported only when Zerodha is actually selected,
    keeping the Groww-only deployment free of a hard kiteconnect dependency.

    The subclass is otherwise 100% the stock KiteTicker: same subscribe/set_mode/
    connect/close, same MODE_* constants, same reconnect kwargs — it only ADDS a
    private REST client + fetch_quote. If the REST client can't be built, fetch_quote
    returns None and the exit path degrades to the LTP (the pre-existing behaviour),
    so a Zerodha run can never be broken by this addition.
    """
    class KiteTickerAdapter(kite_ticker_cls):
        def __init__(self, api_key: str, access_token: str, **kwargs):
            super().__init__(api_key, access_token, **kwargs)
            # Independent REST client: a quote() call survives a stalled WebSocket,
            # which is exactly when the exit path needs a fresh book.
            self._rest_client = None
            try:
                rest = kite_connect_cls(api_key=api_key)
                rest.set_access_token(access_token)
                self._rest_client = rest
            except Exception as e:  # never let this break ticker startup
                log.warning(
                    f"KiteTickerAdapter: REST client init failed ({e}) — on-demand "
                    "depth refresh disabled (LTP fallback still active)"
                )

        def fetch_quote(self, trading_symbol: str) -> dict | None:
            """
            On-demand REST quote (fresh LTP + order-book depth) for one NSE symbol.
            Mirrors GrowwTickerAdapter.fetch_quote's return contract exactly; returns
            None on any failure/empty book so the caller falls back to the LTP.
            """
            if self._rest_client is None:
                return None
            key = f"NSE:{trading_symbol}"
            try:
                resp = self._rest_client.quote([key])
            except Exception as e:
                log.debug(f"fetch_quote({trading_symbol}) failed: {e}")
                return None
            entry = resp.get(key) if isinstance(resp, dict) else None
            return _normalize_kite_quote(entry)

    return KiteTickerAdapter


class ZerodhaBroker(BaseBroker):
    """Zerodha Kite Connect broker. Wraps kiteconnect library."""

    @property
    def name(self) -> str:
        return "zerodha"

    @property
    def display_name(self) -> str:
        return "Zerodha (Kite Connect)"

    def authenticate(self, log) -> str:
        """
        Returns today's Kite access_token.
        Serves cached token if already fetched today; otherwise runs interactive login.
        """
        from dotenv import load_dotenv
        load_dotenv()

        # Check cache — no kiteconnect import needed if token is fresh
        if _CHECKPOINT.exists():
            data = json.loads(_CHECKPOINT.read_text())
            is_today   = data.get("date")   == str(date.today())
            is_zerodha = data.get("broker") == "zerodha"
            token = data.get("access_token") if (is_today and is_zerodha) else None
            if token:
                log.info("Zerodha access token found in cache — proceeding to agent")
                return token

        # Fresh login needed
        api_key    = os.getenv("KITE_API_KEY", "")
        api_secret = os.getenv("KITE_API_SECRET", "")
        if not api_key:
            raise RuntimeError("KITE_API_KEY is not set in your .env file")
        if not api_secret:
            raise RuntimeError("KITE_API_SECRET is not set in your .env file")

        log.info("No cached token for today — starting Zerodha login flow...")
        log.info("Importing kiteconnect for login (first-time, may take a few seconds)...")
        from kiteconnect import KiteConnect
        kite      = KiteConnect(api_key=api_key)
        login_url = kite.login_url()

        print()
        print("=" * 65)
        print("  STEP 1: Open this URL in your browser and log in to Zerodha:")
        print("=" * 65)
        print()
        print(login_url)
        print()
        print()
        print("  After login you will be redirected to a URL like:")
        print("  https://127.0.0.1/?request_token=AbCdXXXX&action=login&status=success")
        print()
        print("  Copy the  request_token  value from that URL.")
        print("=" * 65)
        print()

        request_token = input("  Paste request_token here and press Enter: ").strip()
        if not request_token:
            raise ValueError("No request_token entered")

        log.info("Exchanging request_token for access_token...")
        session      = kite.generate_session(request_token, api_secret=api_secret)
        access_token = session["access_token"]

        _CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        _CHECKPOINT.write_text(json.dumps({"date": str(date.today()), "broker": "zerodha", "access_token": access_token}))
        log.info("Zerodha login successful — token saved")
        return access_token

    def get_credentials(self, args) -> tuple[str, str]:
        """Returns (api_key, access_token) from args / env / checkpoint."""
        from dotenv import load_dotenv
        from config.settings import CHECKPOINT_DIR
        load_dotenv()

        api_key = os.getenv("KITE_API_KEY", "")
        if not api_key:
            raise RuntimeError("KITE_API_KEY not set in .env file")

        if args.token:
            access_token = args.token
            cache = CHECKPOINT_DIR / "access_token.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"date": str(date.today()), "broker": "zerodha", "access_token": access_token}))
            return api_key, access_token

        cache = CHECKPOINT_DIR / "access_token.json"
        if cache.exists():
            data = json.loads(cache.read_text())
            if data.get("date") == str(date.today()) and data.get("broker") == "zerodha":
                return api_key, data["access_token"]

        raise RuntimeError(
            "No Zerodha access token found. Pass --token YOUR_TOKEN or run the login steps:\n"
            "  Step 1: python -c \"from data_pipeline.kite_auth import login_step1; login_step1()\"\n"
            "  Step 2: python -c \"from data_pipeline.kite_auth import login_step2; login_step2('REQUEST_TOKEN')\"\n"
            "  Then: python live/agent.py --token ACCESS_TOKEN"
        )

    def get_api_classes(self) -> tuple[type, type]:
        """
        Returns (KiteConnect, KiteTickerAdapter).

        The ticker is a thin KiteTicker subclass that adds the on-demand
        ``fetch_quote`` hook so Zerodha gets the SAME frozen-book recovery Groww
        has (agent wires it via ``hasattr(new_ws, "fetch_quote")``). The stock
        KiteTicker interface — subscribe/set_mode/connect/close, MODE_FULL, the
        reconnect kwargs — is inherited unchanged.
        """
        from kiteconnect import KiteConnect, KiteTicker
        return KiteConnect, _make_kite_ticker_adapter(KiteTicker, KiteConnect)

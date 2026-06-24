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
import os
from datetime import date
from pathlib import Path

from brokers.base import BaseBroker

_CHECKPOINT = Path(__file__).parent.parent / "checkpoints" / "access_token.json"


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
        """Returns (KiteConnect, KiteTicker) from the kiteconnect library."""
        from kiteconnect import KiteConnect, KiteTicker
        return KiteConnect, KiteTicker

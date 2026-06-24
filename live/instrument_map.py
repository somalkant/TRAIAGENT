"""
Fetch and cache NSE instrument token ↔ symbol mapping.
Kite uses numeric tokens for WebSocket; we need to map symbols to tokens for subscription.
Cache is refreshed once per day (instruments list doesn't change intraday).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kiteconnect import KiteConnect   # only for type checkers; not imported at runtime

log = logging.getLogger(__name__)

_CACHE = Path(__file__).parent.parent / "checkpoints" / "instruments.json"

# Known instrument tokens for indices (constants — don't change)
NIFTY50_TOKEN = 256265


def load_instrument_map(kite, broker_name: str = "zerodha") -> dict[str, int]:
    """
    Returns {tradingsymbol: instrument_token} for all NSE equity instruments.
    Uses cached file if already fetched today BY THE SAME BROKER, otherwise fetches fresh.
    Broker name is stored in the cache — Groww exchange_tokens and Zerodha instrument_tokens
    are different number systems, so mixing them causes zero ticks on the WebSocket.

    For Groww: also saves/restores the adapter's internal _token_to_groww_sym map so that
    historical_data() works correctly when loading from cache (without re-fetching instruments).
    """
    if _CACHE.exists():
        data = json.loads(_CACHE.read_text())
        if data.get("date") == str(date.today()) and data.get("broker") == broker_name:
            # Restore Groww adapter's internal symbol maps from cache so historical_data() works
            if broker_name == "groww" and hasattr(kite, "_token_to_groww_sym"):
                kite._token_to_groww_sym = {
                    int(k): v for k, v in data.get("groww_sym_map", {}).items()
                }
                kite._token_to_symbol = {
                    int(k): v for k, v in data.get("token_to_symbol", {}).items()
                }
            log.info(f"Instrument map: loaded {len(data['map'])} symbols from cache ({broker_name})")
            return data["map"]

    log.info(f"Fetching NSE instrument list from {broker_name} API...")
    instruments = kite.instruments("NSE")

    imap: dict[str, int] = {}
    for inst in instruments:
        if inst.get("instrument_type") == "EQ":
            imap[inst["tradingsymbol"]] = inst["instrument_token"]

    cache_data: dict = {"date": str(date.today()), "broker": broker_name, "map": imap}
    # For Groww: persist the internal symbol maps so they survive cache restores
    if broker_name == "groww" and hasattr(kite, "_token_to_groww_sym"):
        cache_data["groww_sym_map"]    = {str(k): v for k, v in kite._token_to_groww_sym.items()}
        cache_data["token_to_symbol"]  = {str(k): v for k, v in kite._token_to_symbol.items()}

    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(cache_data))
    log.info(f"Instrument map cached: {len(imap)} NSE equities ({broker_name})")
    return imap

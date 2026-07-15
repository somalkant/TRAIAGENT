"""
One-time fetch of the current F&O-eligible stock list — used as the SHORT-side
universe for the Top-10 backtest (top10_backtest/universe.py::short_universe).

Usage:
    python scripts/build_fno_list.py [--broker zerodha|groww]

Requires a working broker login (same auth flow as run_live.py). Writes
config/fno_symbols.csv (one column: symbol) — the underlying equity
tradingsymbol for every stock with an NFO futures contract, intersected with
our own equity universe (config/universe.csv) to drop index futures
(NIFTY, BANKNIFTY, FINNIFTY, etc.).
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import BASE_DIR

OUT_FILE      = BASE_DIR / "config" / "fno_symbols.csv"
UNIVERSE_FILE = BASE_DIR / "config" / "universe.csv"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="zerodha", choices=["zerodha", "groww"])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
    log = logging.getLogger(__name__)

    from brokers import get_broker
    broker = get_broker(args.broker)
    access_token = broker.authenticate(log)

    KiteConnect, _ = broker.get_api_classes()
    args.token = access_token
    api_key, access_token = broker.get_credentials(args)
    client = KiteConnect(api_key=api_key)
    client.set_access_token(access_token)

    log.info("Fetching NFO instrument list...")
    nfo = client.instruments("NFO")
    fut_names = {
        str(inst["name"]).strip().upper()
        for inst in nfo
        if inst.get("instrument_type") == "FUT" and inst.get("name")
    }
    log.info(f"{len(fut_names)} unique underlyings with an NFO futures contract")

    universe = pd.read_csv(UNIVERSE_FILE)
    equity_symbols = set(universe["tradingsymbol"].astype(str).str.upper())

    fno_symbols = sorted(fut_names & equity_symbols)
    dropped = fut_names - equity_symbols
    if dropped:
        preview = sorted(dropped)[:10]
        log.info(f"Dropped {len(dropped)} non-equity underlyings (indices etc.): "
                 f"{preview}{'...' if len(dropped) > 10 else ''}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"symbol": fno_symbols}).to_csv(OUT_FILE, index=False)
    log.info(f"Wrote {len(fno_symbols)} F&O-eligible symbols to {OUT_FILE}")


if __name__ == "__main__":
    main()

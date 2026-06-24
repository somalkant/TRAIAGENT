"""
Persists today's live 5-min candle bars so the agent can resume after a crash
or intentional restart without losing bars already built from KiteTicker ticks.

Checkpoint file: checkpoints/live_candles_YYYY-MM-DD.json
Written after every bar close (every 5 minutes).
On restart, bars are seeded back into each CandleBuilder before market loop starts.
"""
import json
import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

_CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints"


def save_candles(today: date, builders: dict) -> None:
    """
    Persist all builders' closed bars to today's checkpoint.
    builders: {symbol: CandleBuilder}  — include NIFTY50 builder here too.
    """
    payload: dict = {"date": str(today), "symbols": {}}
    for symbol, builder in builders.items():
        bars = builder.closed_bars
        if bars:
            payload["symbols"][symbol] = [
                {**b, "datetime": b["datetime"].isoformat()} for b in bars
            ]
    path = _CHECKPOINT_DIR / f"live_candles_{today}.json"
    try:
        _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    except Exception as e:
        log.warning(f"Candle checkpoint save failed: {e}")


def load_candles(today: date) -> dict[str, list[dict]]:
    """
    Load today's checkpoint.
    Returns {symbol: [bar_dict, ...]} with datetime as Python datetime objects.
    Returns {} if checkpoint doesn't exist or is stale.
    """
    path = _CHECKPOINT_DIR / f"live_candles_{today}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        if data.get("date") != str(today):
            return {}
        result: dict[str, list[dict]] = {}
        for symbol, bars in data.get("symbols", {}).items():
            result[symbol] = [
                {**b, "datetime": datetime.fromisoformat(b["datetime"])} for b in bars
            ]
        return result
    except Exception as e:
        log.warning(f"Candle checkpoint load failed: {e}")
        return {}

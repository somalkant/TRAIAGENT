"""
Live trade logging for the Top-10 agent — mirrors live/paper_logger.py's split
(open-position checkpoint + closed-trade CSV), but keyed by strategy since up
to 10 strategies can each have an independent open LONG and open SHORT
position (vs the old agent's single LONG/SHORT slot).
"""
import json
import logging
from datetime import date

import pandas as pd

from config.settings import TRADE_LOG_DIR, CHECKPOINT_DIR
from backtester.cost_model import net_pnl
from top10_backtest.costs import cost_breakdown

log = logging.getLogger(__name__)

TRADES_FILE       = TRADE_LOG_DIR / "top10_live_trades.csv"
OPEN_TRADES_CACHE = CHECKPOINT_DIR / "top10_live_open_trades.json"

COLUMNS = [
    "date", "side", "strategy", "symbol", "signal_time", "entry_time", "entry_price",
    "qty", "notional_rs", "stop", "target", "exit_time", "exit_price", "exit_reason",
    "result", "gross_pnl_rs", "total_cost_rs", "net_pnl_rs", "net_pnl_pct",
    "fill_slippage", "brokerage", "stt", "exchange", "sebi", "gst", "stamp", "slippage",
]


def save_open_trades(trade_date: date, state_snapshot: dict) -> None:
    """Persist the whole {strategy: {long, short, long_placed, short_placed}} dict."""
    payload = {"date": str(trade_date), "state": state_snapshot}
    OPEN_TRADES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OPEN_TRADES_CACHE.write_text(json.dumps(payload, default=str))


def load_open_trades() -> tuple[date | None, dict]:
    """Returns (trade_date, state_dict). state_dict is {} if no checkpoint or stale (not today)."""
    if not OPEN_TRADES_CACHE.exists():
        return None, {}
    try:
        data = json.loads(OPEN_TRADES_CACHE.read_text())
        saved_date = date.fromisoformat(data["date"])
        if saved_date != date.today():
            return None, {}
        return saved_date, data.get("state", {})
    except Exception as e:
        log.warning(f"Could not read open-trades checkpoint: {e}")
        return None, {}


def clear_open_trades() -> None:
    if OPEN_TRADES_CACHE.exists():
        OPEN_TRADES_CACHE.unlink()


def log_closed_trade(trade_date: date, strategy_name: str, side: str, rec: dict,
                      exit_price: float, exit_reason: str, exit_time: str) -> None:
    """
    Append a completed trade to top10_live_trades.csv.
    Prefers the order-book-settled weighted avg fill price (real holding price)
    over the raw signal entry, once _settle_fills() has confirmed a fill —
    same convention as the existing live/paper_logger.py.
    """
    sig       = rec["signal"]
    entry     = float(rec.get("_avg_fill_price") or sig["entry"])
    qty       = int(rec["shares"])
    notional  = float(rec["position_rs"])
    direction = 1 if side == "LONG" else -1

    net   = net_pnl(entry, exit_price, qty, direction=direction)
    gross = (exit_price - entry) * qty * direction
    cost  = round(gross - net, 2)
    costs = cost_breakdown(entry, exit_price, qty, direction)
    fill_slip = (entry - float(sig["entry"])) * direction

    result = "EXACT_WIN" if exit_reason == "TARGET_HIT" else ("WIN" if net > 0 else "LOSS")
    net_pnl_pct = round(net / notional * 100, 2) if notional else 0.0

    row = {
        "date": str(trade_date), "side": side, "strategy": strategy_name, "symbol": rec["symbol"],
        "signal_time": sig["signal_time"], "entry_time": rec.get("entry_time", ""),
        "entry_price": entry, "qty": qty, "notional_rs": notional,
        "stop": sig["stop"], "target": sig["target"],
        "exit_time": exit_time, "exit_price": round(exit_price, 2), "exit_reason": exit_reason,
        "result": result, "gross_pnl_rs": round(gross, 2), "total_cost_rs": cost,
        "net_pnl_rs": round(net, 2), "net_pnl_pct": net_pnl_pct,
        "fill_slippage": round(fill_slip, 2),
        **{k: round(v, 2) for k, v in costs.items()},
    }

    new_df = pd.DataFrame([row], columns=COLUMNS)
    TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    header = not TRADES_FILE.exists()
    new_df.to_csv(TRADES_FILE, mode="a", header=header, index=False)

    log.info(
        f"TRADE CLOSED [{side}] {strategy_name}: {rec['symbol']} | {exit_reason} @ {exit_price:.2f} | "
        f"P&L Rs {net:+,.0f} ({net_pnl_pct:+.2f}%) | {result}"
    )

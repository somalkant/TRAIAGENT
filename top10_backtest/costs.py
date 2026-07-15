"""
Itemized transaction cost breakdown for trade-log rows.

Same rates/formula as backtester/cost_model.py (which only returns a single
summed total) — kept here so this package doesn't reach into backtester/
internals for something as simple as re-deriving individual line items.
"""
from config.settings import (
    BROKERAGE_PER_LEG, STT_RATE_SELL, EXCHANGE_RATE, SEBI_RATE,
    GST_RATE, STAMP_RATE_BUY, SLIPPAGE_PER_SIDE,
)


def cost_breakdown(entry: float, exit_price: float, qty: int, direction: int) -> dict:
    buy_val  = entry * qty if direction == 1 else exit_price * qty
    sell_val = exit_price * qty if direction == 1 else entry * qty

    brokerage = BROKERAGE_PER_LEG * 2
    stt       = sell_val * STT_RATE_SELL
    exchange  = (buy_val + sell_val) * EXCHANGE_RATE
    sebi      = (buy_val + sell_val) * SEBI_RATE
    gst       = (brokerage + exchange) * GST_RATE
    stamp     = buy_val * STAMP_RATE_BUY
    slippage  = (buy_val + sell_val) * SLIPPAGE_PER_SIDE

    return {
        "brokerage": brokerage, "stt": stt, "exchange": exchange, "sebi": sebi,
        "gst": gst, "stamp": stamp, "slippage": slippage,
    }

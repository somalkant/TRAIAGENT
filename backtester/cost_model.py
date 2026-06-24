"""Transaction cost calculator — includes all real NSE charges."""
from config.settings import (BROKERAGE_PER_LEG, STT_RATE_SELL, EXCHANGE_RATE,
                              SEBI_RATE, GST_RATE, STAMP_RATE_BUY, SLIPPAGE_PER_SIDE)


def total_cost(buy_value: float, sell_value: float) -> float:
    brokerage = BROKERAGE_PER_LEG * 2
    stt       = sell_value * STT_RATE_SELL
    exchange  = (buy_value + sell_value) * EXCHANGE_RATE
    sebi      = (buy_value + sell_value) * SEBI_RATE
    gst       = (brokerage + exchange) * GST_RATE
    stamp     = buy_value * STAMP_RATE_BUY
    slippage  = (buy_value + sell_value) * SLIPPAGE_PER_SIDE
    return brokerage + stt + exchange + sebi + gst + stamp + slippage


def net_pnl(entry: float, exit_price: float, shares: int, direction: int = 1) -> float:
    buy_val  = entry * shares if direction == 1 else exit_price * shares
    sell_val = exit_price * shares if direction == 1 else entry * shares
    gross    = (exit_price - entry) * shares * direction
    cost     = total_cost(buy_val, sell_val)
    return gross - cost

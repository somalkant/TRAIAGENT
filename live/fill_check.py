"""
Fill availability check for paper trading.

Uses per-price-level market depth from GrowwFeed StocksMarketDepthProto
(subscribe_market_depth), updated continuously via the on_depth callback.

  For LONG  : sums qty from sell (ask) levels at price <= entry_price
  For SHORT : sums qty from buy  (bid) levels at price >= entry_price

Returns FILLED / NOT_FILLED / DEPTH_UNAVAILABLE — never blocks the trade.
"""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def check_fill(dm, symbol: str, entry_price: float, shares: int, direction: str) -> dict:
    """
    dm        : LiveDataManager (has get_depth())
    direction : "LONG" or "SHORT"

    Returns dict:
      fillable  : bool | None  (None = depth not yet received, do not block trade)
      avail_qty : int
      status    : "FILLED" | "NOT_FILLED" | "DEPTH_UNAVAILABLE"
      msg       : one-liner for the log
    """
    depth = dm.get_depth(symbol) if hasattr(dm, "get_depth") else None

    if depth is None:
        return {
            "fillable":  None,
            "avail_qty": 0,
            "status":    "DEPTH_UNAVAILABLE",
            "msg":       f"market depth not yet received for {symbol}",
        }

    if direction == "LONG":
        # Need sellers at or below our entry price
        avail_qty = sum(
            int(lvl["qty"])
            for lvl in depth.get("sell", [])
            if lvl["price"] <= entry_price + 0.05
        )
        side_label = "sellers (ask)"
    else:
        # Need buyers at or above our entry price
        avail_qty = sum(
            int(lvl["qty"])
            for lvl in depth.get("buy", [])
            if lvl["price"] >= entry_price - 0.05
        )
        side_label = "buyers (bid)"

    # Build a short depth snapshot for the log (best 3 levels)
    if direction == "LONG":
        levels_str = _fmt_levels(depth.get("sell", [])[:3], "ask")
    else:
        levels_str = _fmt_levels(depth.get("buy",  [])[:3], "bid")

    if avail_qty >= shares:
        return {
            "fillable":  True,
            "avail_qty": avail_qty,
            "status":    "FILLED",
            "msg": (
                f"{side_label} avail={avail_qty:,} >= need={shares} "
                f"@ ₹{entry_price:.2f} → FILLED  [{levels_str}]"
            ),
        }
    else:
        return {
            "fillable":  False,
            "avail_qty": avail_qty,
            "status":    "NOT_FILLED",
            "msg": (
                f"{side_label} avail={avail_qty:,} < need={shares} "
                f"@ ₹{entry_price:.2f} → NOT FILLED  [{levels_str}]"
            ),
        }


def _fmt_levels(levels: list[dict], side: str) -> str:
    if not levels:
        return f"no {side} levels"
    parts = [f"₹{l['price']:.2f}×{int(l['qty'])}" for l in levels]
    return f"{side}: " + " | ".join(parts)

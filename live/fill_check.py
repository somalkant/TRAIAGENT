"""
Fill availability check for paper trading.

Uses per-price-level market depth from GrowwFeed StocksMarketDepthProto
(subscribe_market_depth), updated continuously via the on_depth callback.

  check_fill()    — snapshot check at placement time; also shows "best available" scenario
  simulate_fill() — walk the book level-by-level; returns filled qty + weighted avg price

Flow:
  1. At trade placement   → check_fill() → FILLED / NOT_FILLED + best-ask/bid scenario
  2. At next bar (+5 min) → _settle_fills() in agent.py re-checks depth → FILL SETTLE log
     with final fill verdict, avg holding price, and slippage vs signal entry.

Returns FILLED / NOT_FILLED / DEPTH_UNAVAILABLE — never blocks the trade.
"""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def simulate_fill(depth: dict, target_qty: int, entry_price: float,
                  direction: str, tolerance: float = 0.05) -> dict:
    """
    Walk the order book level-by-level to simulate filling target_qty shares.

    Two passes:
      in_range  — levels at/within entry_price ± tolerance (signal-entry fill)
      best_avail — all levels, no price limit (market-price fill)

    Returns:
      filled_qty  : shares fillable within tolerance of entry_price
      avg_price   : weighted avg fill price (0.0 if nothing filled)
      best_qty    : shares fillable at best available market price
      best_avg    : weighted avg fill price at best market (0.0 if nothing)
      best_price  : top-of-book price (best ask for LONG, best bid for SHORT)
    """
    if direction == "LONG":
        in_range = [l for l in depth.get("sell", []) if l["price"] <= entry_price + tolerance]
        all_side = depth.get("sell", [])
    else:
        in_range = [l for l in depth.get("buy",  []) if l["price"] >= entry_price - tolerance]
        all_side = depth.get("buy",  [])

    def _walk(levels: list, qty: int) -> tuple[int, float]:
        filled, wsum = 0, 0.0
        for lvl in levels:
            if qty <= 0:
                break
            take    = min(int(lvl["qty"]), qty)
            filled += take
            wsum   += float(lvl["price"]) * take
            qty    -= take
        return filled, (wsum / filled if filled else 0.0)

    filled_qty, avg_price = _walk(in_range, target_qty)
    best_qty,   best_avg  = _walk(all_side, target_qty)
    best_price = float(all_side[0]["price"]) if all_side else None

    return {
        "filled_qty": filled_qty,
        "avg_price":  avg_price,
        "best_qty":   best_qty,
        "best_avg":   best_avg,
        "best_price": best_price,
    }


def check_fill(dm, symbol: str, entry_price: float, shares: int,
               direction: str) -> dict:
    """
    dm        : LiveDataManager (has get_depth())
    direction : "LONG" or "SHORT"

    Returns dict:
      fillable   : bool | None  (None = depth unavailable, do not block trade)
      filled_qty : shares fillable at/near entry_price
      avg_price  : weighted avg fill price (0.0 if nothing)
      best_qty   : shares fillable at best market price
      best_avg   : weighted avg at best market (0.0 if nothing)
      best_price : top-of-book price
      status     : "FILLED" | "NOT_FILLED" | "DEPTH_UNAVAILABLE"
      msg        : one-liner for the log
    """
    depth = dm.get_depth(symbol) if hasattr(dm, "get_depth") else None

    if depth is None:
        return {
            "fillable":   None,
            "filled_qty": 0,
            "avg_price":  0.0,
            "best_qty":   0,
            "best_avg":   0.0,
            "best_price": None,
            "status":     "DEPTH_UNAVAILABLE",
            "msg":        f"market depth not yet received for {symbol}",
        }

    sim        = simulate_fill(depth, shares, entry_price, direction)
    side       = "ask"           if direction == "LONG" else "bid"
    side_label = "sellers (ask)" if direction == "LONG" else "buyers (bid)"
    book_key   = "sell"          if direction == "LONG" else "buy"
    levels_str = _fmt_levels(depth.get(book_key, [])[:3], side)

    if sim["filled_qty"] >= shares:
        fillable, status = True, "FILLED"
        msg = (
            f"{side_label} avail={sim['filled_qty']:,} >= need={shares} "
            f"@ ₹{entry_price:.2f} → FILLED | avg ₹{sim['avg_price']:.2f}  [{levels_str}]"
        )
    else:
        fillable, status = False, "NOT_FILLED"
        # Show what accepting the best available price would achieve
        if sim["best_price"] is not None and sim["best_qty"] >= shares:
            slip = (sim["best_avg"] - entry_price if direction == "LONG"
                    else entry_price - sim["best_avg"])
            best_note = (
                f"at best {side} ₹{sim['best_price']:.2f}: fills @ avg ₹{sim['best_avg']:.2f} "
                f"(slip ₹{slip:+.2f})"
            )
        elif sim["best_qty"] > 0:
            best_note = f"even at best {side}: only {sim['best_qty']:,}/{shares} avail"
        else:
            best_note = f"no {side} levels in book"
        msg = (
            f"{side_label} avail={sim['filled_qty']:,} < need={shares} "
            f"@ ₹{entry_price:.2f} → NOT FILLED  [{levels_str}] | {best_note}"
        )

    return {
        "fillable":   fillable,
        "filled_qty": sim["filled_qty"],
        "avg_price":  sim["avg_price"],
        "best_qty":   sim["best_qty"],
        "best_avg":   sim["best_avg"],
        "best_price": sim["best_price"],
        "status":     status,
        "msg":        msg,
    }


def _fmt_levels(levels: list[dict], side: str) -> str:
    if not levels:
        return f"no {side} levels"
    parts = [f"₹{l['price']:.2f}×{int(l['qty'])}" for l in levels]
    return f"{side}: " + " | ".join(parts)

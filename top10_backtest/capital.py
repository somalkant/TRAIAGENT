"""
Per-strategy capital ledger — Rs 10L per strategy, split Rs 5L long / Rs 5L short.

Capital is fixed per day (not compounding): every trade sizes off a flat
Rs 5,00,000 notional regardless of that strategy's running P&L. Cumulative
P&L is tracked separately, per strategy and per side.
"""
from __future__ import annotations

POOL_PER_SIDE = 5_00_000.0   # Rs 5L, fixed, non-compounding


def size(entry_price: float) -> tuple[int, float]:
    """Full-capital-deployed sizing: qty = floor(pool / entry_price)."""
    if entry_price <= 0:
        return 0, 0.0
    qty = int(POOL_PER_SIDE // entry_price)
    return qty, round(qty * entry_price, 2)


class StrategyLedger:
    """Running net P&L per strategy, per side (LONG/SHORT), across the whole backtest."""

    def __init__(self, strategy_names: list[str]):
        self._pnl = {name: {"LONG": 0.0, "SHORT": 0.0} for name in strategy_names}
        self._trade_count = {name: {"LONG": 0, "SHORT": 0} for name in strategy_names}

    def record(self, strategy: str, side: str, net_pnl_rs: float) -> None:
        self._pnl[strategy][side] += net_pnl_rs
        self._trade_count[strategy][side] += 1

    def running_pnl(self, strategy: str, side: str) -> float:
        return self._pnl[strategy][side]

    def summary(self) -> dict:
        return {
            name: {
                "long_pnl":     round(self._pnl[name]["LONG"], 2),
                "short_pnl":    round(self._pnl[name]["SHORT"], 2),
                "long_trades":  self._trade_count[name]["LONG"],
                "short_trades": self._trade_count[name]["SHORT"],
            }
            for name in self._pnl
        }

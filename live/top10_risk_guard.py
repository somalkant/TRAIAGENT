"""
Risk guard for the Top-10 live agent.

Two independent layers:
  1. Whole-system halt   — same pattern as live/risk_guard.py, thresholds scaled
                           to the 10-strategy system's larger capital base.
  2. Per-strategy/side halt — new: each of the 10 strategies runs its own
                           independent Rs 5L long / Rs 5L short pool, so a bad
                           pool can be halted without stopping the other 9.

Both are next-day gates, not mid-session circuit breakers — checked once at
agent startup, since a side's single daily trade slot is already used by the
time a loss is realized anyway.

Halt files (checkpoints/):
  TOP10_HALT_DAILY.flag / TOP10_HALT_MONTHLY.flag — whole-system halt
  top10_halt_state.json                           — per-strategy/side halt state

To resume from CMD:
  del checkpoints\\TOP10_HALT_DAILY.flag
  del checkpoints\\TOP10_HALT_MONTHLY.flag
  (edit/delete checkpoints\\top10_halt_state.json to clear specific strategies)
"""
import json
import logging
import sys
from datetime import date

import pandas as pd

from config.settings import (
    CHECKPOINT_DIR,
    TOP10_SYSTEM_DAILY_LOSS_LIMIT, TOP10_SYSTEM_MONTHLY_LOSS_LIMIT,
    TOP10_PER_STRATEGY_DAILY_LOSS_LIMIT, TOP10_PER_STRATEGY_MONTHLY_LOSS_LIMIT,
)
from live.top10_logger import TRADES_FILE

log = logging.getLogger(__name__)

DAILY_HALT_FLAG    = CHECKPOINT_DIR / "TOP10_HALT_DAILY.flag"
MONTHLY_HALT_FLAG  = CHECKPOINT_DIR / "TOP10_HALT_MONTHLY.flag"
STRATEGY_HALT_FILE = CHECKPOINT_DIR / "top10_halt_state.json"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_trades() -> pd.DataFrame:
    if not TRADES_FILE.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(TRADES_FILE, parse_dates=["date"], on_bad_lines="skip")
    except Exception:
        return pd.DataFrame()


def _pnl_sum(df: pd.DataFrame, today: date, month_scope: bool,
             strategy: str | None = None, side: str | None = None) -> float:
    if df.empty or "net_pnl_rs" not in df.columns:
        return 0.0
    if month_scope:
        month_start = today.replace(day=1)
        mask = (df["date"].dt.date >= month_start) & (df["date"].dt.date <= today)
    else:
        mask = df["date"].dt.date == today
    if strategy is not None:
        mask &= df["strategy"] == strategy
    if side is not None:
        mask &= df["side"] == side
    return float(df.loc[mask, "net_pnl_rs"].sum())


def _banner(lines: list[str], level: str = "error") -> None:
    fn = log.error if level == "error" else log.warning
    fn("=" * 65)
    for line in lines:
        fn(f"  {line}")
    fn("=" * 65)


def _load_strategy_halts_raw() -> dict[str, str]:
    if not STRATEGY_HALT_FILE.exists():
        return {}
    try:
        return json.loads(STRATEGY_HALT_FILE.read_text())
    except Exception:
        return {}


def _save_strategy_halts_raw(halts: dict[str, str]) -> None:
    STRATEGY_HALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_HALT_FILE.write_text(json.dumps(halts))


def _write_monthly_flag(mtd: float, today: date) -> None:
    reason = (f"Whole-system monthly loss Rs {mtd:,.0f} exceeded limit "
              f"Rs -{TOP10_SYSTEM_MONTHLY_LOSS_LIMIT:,.0f} on {today}.")
    MONTHLY_HALT_FLAG.write_text(reason)
    _banner([
        f"TOP10 SYSTEM MONTHLY LOSS LIMIT BREACHED (Rs {mtd:,.0f})",
        f"Resume: del {MONTHLY_HALT_FLAG}",
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_risk_limits(today: date, strategy_names: list[str]) -> dict[tuple[str, str], str]:
    """
    Call at agent startup. Whole-system breach exits the process (sys.exit(1)),
    same as the old agent. Per-strategy/side halts are returned as a dict —
    {(strategy, side): reason} — so the caller can skip scanning those sides
    without stopping the rest of the system.
    """
    df  = _load_trades()
    mtd = _pnl_sum(df, today, month_scope=True)

    log.info("-" * 65)
    log.info(f"  TOP10 RISK CHECK — {today}")
    log.info(f"  MTD P&L (whole system): Rs {mtd:+,.0f}  /  limit Rs -{TOP10_SYSTEM_MONTHLY_LOSS_LIMIT:,.0f}")
    log.info("-" * 65)

    if MONTHLY_HALT_FLAG.exists():
        _banner([
            "*** TOP10 SYSTEM MONTHLY HALT IN EFFECT ***",
            MONTHLY_HALT_FLAG.read_text().strip(),
            "", f"Resume: del {MONTHLY_HALT_FLAG}",
        ])
        sys.exit(1)

    if DAILY_HALT_FLAG.exists():
        _banner([
            "*** TOP10 SYSTEM DAILY HALT IN EFFECT ***",
            DAILY_HALT_FLAG.read_text().strip(),
            "", f"Resume: del {DAILY_HALT_FLAG}",
        ], level="warning")
        sys.exit(1)

    if mtd < -TOP10_SYSTEM_MONTHLY_LOSS_LIMIT:
        _write_monthly_flag(mtd, today)
        sys.exit(1)

    log.info("  Whole-system risk limits OK.")

    raw = _load_strategy_halts_raw()
    halted: dict[tuple[str, str], str] = {}
    for key, reason in raw.items():
        strategy, side = key.rsplit("_", 1)
        halted[(strategy, side)] = reason
        log.warning(f"  HALTED [{strategy} {side}]: {reason}")

    return halted


def write_eod_risk_check(today: date, strategy_names: list[str]) -> None:
    """Call at end of day. Whole-system + per-strategy/side EOD evaluation."""
    df        = _load_trades()
    mtd_all   = _pnl_sum(df, today, month_scope=True)
    today_all = _pnl_sum(df, today, month_scope=False)

    log.info("-" * 65)
    log.info(f"  TOP10 EOD RISK CHECK — {today}")
    log.info(f"  Today's P&L (whole system): Rs {today_all:+,.0f}  (limit Rs -{TOP10_SYSTEM_DAILY_LOSS_LIMIT:,.0f})")
    log.info(f"  MTD P&L     (whole system): Rs {mtd_all:+,.0f}  (limit Rs -{TOP10_SYSTEM_MONTHLY_LOSS_LIMIT:,.0f})")

    if mtd_all < -TOP10_SYSTEM_MONTHLY_LOSS_LIMIT and not MONTHLY_HALT_FLAG.exists():
        _write_monthly_flag(mtd_all, today)

    if today_all < -TOP10_SYSTEM_DAILY_LOSS_LIMIT and not DAILY_HALT_FLAG.exists():
        reason = (f"Whole-system daily loss Rs {today_all:,.0f} exceeded limit "
                  f"Rs -{TOP10_SYSTEM_DAILY_LOSS_LIMIT:,.0f} on {today}.")
        DAILY_HALT_FLAG.write_text(reason)
        _banner([
            f"TOP10 SYSTEM DAILY LOSS LIMIT HIT (Rs {today_all:,.0f})",
            f"Resume: del {DAILY_HALT_FLAG}",
        ], level="warning")

    # ── per-strategy / per-side ──────────────────────────────────────────────
    halts = _load_strategy_halts_raw()
    for strategy in strategy_names:
        for side in ("LONG", "SHORT"):
            key = f"{strategy}_{side}"
            if key in halts:
                continue  # already halted from a prior day
            day_pnl = _pnl_sum(df, today, month_scope=False, strategy=strategy, side=side)
            mtd_pnl = _pnl_sum(df, today, month_scope=True,  strategy=strategy, side=side)
            if mtd_pnl < -TOP10_PER_STRATEGY_MONTHLY_LOSS_LIMIT:
                halts[key] = (f"Monthly loss Rs {mtd_pnl:,.0f} exceeded "
                              f"Rs -{TOP10_PER_STRATEGY_MONTHLY_LOSS_LIMIT:,.0f}")
                log.warning(f"  HALTING [{strategy} {side}] for next session: {halts[key]}")
            elif day_pnl < -TOP10_PER_STRATEGY_DAILY_LOSS_LIMIT:
                halts[key] = (f"Daily loss Rs {day_pnl:,.0f} exceeded "
                              f"Rs -{TOP10_PER_STRATEGY_DAILY_LOSS_LIMIT:,.0f} on {today}")
                log.warning(f"  HALTING [{strategy} {side}] for next session: {halts[key]}")

    _save_strategy_halts_raw(halts)
    log.info("-" * 65)

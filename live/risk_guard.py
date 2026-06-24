"""
Risk guard — daily and monthly loss limits for the live paper trading agent.

Startup check  : check_risk_limits(today)   — call before market hours
End-of-day check: write_eod_risk_check(today) — call after trade is logged

Halt flag files (in checkpoints/):
  HALT_DAILY.flag   — today's trade lost more than DAILY_LOSS_LIMIT
  HALT_MONTHLY.flag — MTD P&L crossed below MONTHLY_LOSS_LIMIT

To resume from CMD:
  del checkpoints\\HALT_DAILY.flag
  del checkpoints\\HALT_MONTHLY.flag
"""

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from config.settings import DAILY_LOSS_LIMIT, MONTHLY_LOSS_LIMIT, CHECKPOINT_DIR
from live.paper_logger import LIVE_TRADES_FILE

log = logging.getLogger(__name__)

DAILY_HALT_FLAG   = CHECKPOINT_DIR / "HALT_DAILY.flag"
MONTHLY_HALT_FLAG = CHECKPOINT_DIR / "HALT_MONTHLY.flag"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_trades() -> pd.DataFrame:
    if not LIVE_TRADES_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(LIVE_TRADES_FILE, parse_dates=["date"])
        return df
    except Exception:
        return pd.DataFrame()


def _mtd_pnl(df: pd.DataFrame, today: date) -> float:
    """Sum pnl_rs from 1st of current month through today."""
    if df.empty or "pnl_rs" not in df.columns:
        return 0.0
    month_start = today.replace(day=1)
    mask = (df["date"].dt.date >= month_start) & (df["date"].dt.date <= today)
    return float(df.loc[mask, "pnl_rs"].sum())


def _today_pnl(df: pd.DataFrame, today: date) -> float:
    """Sum pnl_rs for today only."""
    if df.empty or "pnl_rs" not in df.columns:
        return 0.0
    mask = df["date"].dt.date == today
    return float(df.loc[mask, "pnl_rs"].sum())


def _banner(lines: list[str], level: str = "error") -> None:
    fn = log.error if level == "error" else log.warning
    fn("=" * 65)
    for line in lines:
        fn(f"  {line}")
    fn("=" * 65)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_risk_limits(today: date) -> None:
    """
    Call at agent startup (before pre-market filter).
    Prints MTD P&L summary, then exits if any halt flag is active.
    Monthly limit is also re-checked live in case the flag was manually cleared
    but the loss persists.
    """
    df  = _load_trades()
    mtd = _mtd_pnl(df, today)
    mtd_sign = "+" if mtd >= 0 else ""
    month_label = today.strftime("%b %Y")

    log.info("-" * 65)
    log.info(f"  RISK CHECK — {today}")
    log.info(f"  MTD P&L  ({month_label}): Rs {mtd_sign}{mtd:,.0f}"
             f"  /  monthly limit Rs -{MONTHLY_LOSS_LIMIT:,.0f}")
    log.info(f"  Daily loss limit : Rs -{DAILY_LOSS_LIMIT:,.0f} per session")
    log.info("-" * 65)

    # ── Check monthly halt flag ──────────────────────────────────────────────
    if MONTHLY_HALT_FLAG.exists():
        reason = MONTHLY_HALT_FLAG.read_text().strip()
        _banner([
            "*** MONTHLY HALT IN EFFECT ***",
            reason,
            f"MTD P&L ({month_label}): Rs {mtd_sign}{mtd:,.0f}",
            "",
            "Review your trades for the month, then resume by running:",
            f"  del {MONTHLY_HALT_FLAG}",
            "Then restart the agent.",
        ])
        sys.exit(1)

    # ── Check daily halt flag ────────────────────────────────────────────────
    if DAILY_HALT_FLAG.exists():
        reason = DAILY_HALT_FLAG.read_text().strip()
        _banner([
            "*** DAILY HALT IN EFFECT ***",
            reason,
            "",
            "Review yesterday's trade, then resume by running:",
            f"  del {DAILY_HALT_FLAG}",
            "Then restart the agent.",
        ], level="warning")
        sys.exit(1)

    # ── Live monthly limit check (flag may have been cleared but loss persists) ─
    if mtd < -MONTHLY_LOSS_LIMIT:
        _write_monthly_flag(mtd, today)
        sys.exit(1)

    log.info("  Risk limits OK — proceeding.")
    log.info("-" * 65)


def write_eod_risk_check(today: date) -> None:
    """
    Call at end of day AFTER the trade is logged to live_paper_trades.csv.
    Evaluates today's P&L and MTD P&L against limits.
    Writes halt flag files when limits are breached.
    """
    df        = _load_trades()
    mtd       = _mtd_pnl(df, today)
    today_val = _today_pnl(df, today)
    month_label = today.strftime("%b %Y")
    mtd_sign  = "+" if mtd >= 0 else ""
    day_sign  = "+" if today_val >= 0 else ""

    log.info("-" * 65)
    log.info(f"  EOD RISK CHECK — {today}")
    log.info(f"  Today's P&L     : Rs {day_sign}{today_val:,.0f}"
             f"  (limit Rs -{DAILY_LOSS_LIMIT:,.0f})")
    log.info(f"  MTD P&L ({month_label}): Rs {mtd_sign}{mtd:,.0f}"
             f"  (limit Rs -{MONTHLY_LOSS_LIMIT:,.0f})")

    halted = False

    # ── Monthly limit ────────────────────────────────────────────────────────
    if mtd < -MONTHLY_LOSS_LIMIT and not MONTHLY_HALT_FLAG.exists():
        _write_monthly_flag(mtd, today)
        halted = True

    # ── Daily limit ──────────────────────────────────────────────────────────
    if today_val < -DAILY_LOSS_LIMIT and not DAILY_HALT_FLAG.exists():
        reason = (f"Daily loss Rs {today_val:,.0f} exceeded limit "
                  f"Rs -{DAILY_LOSS_LIMIT:,.0f} on {today}. "
                  f"Review before trading tomorrow.")
        DAILY_HALT_FLAG.write_text(reason)
        _banner([
            f"DAILY LOSS LIMIT HIT  (Rs {today_val:,.0f})",
            f"Limit: Rs -{DAILY_LOSS_LIMIT:,.0f}",
            "",
            "Agent will NOT trade tomorrow until you review and run:",
            f"  del {DAILY_HALT_FLAG}",
        ], level="warning")
        halted = True

    if not halted:
        log.info("  All risk limits within bounds.")
    log.info("-" * 65)


# ─────────────────────────────────────────────────────────────────────────────

def _write_monthly_flag(mtd: float, today: date) -> None:
    reason = (f"Monthly loss Rs {mtd:,.0f} exceeded limit "
              f"Rs -{MONTHLY_LOSS_LIMIT:,.0f} on {today}. "
              f"Human review required before resuming.")
    MONTHLY_HALT_FLAG.write_text(reason)
    _banner([
        f"MONTHLY LOSS LIMIT BREACHED  (Rs {mtd:,.0f})",
        f"Limit: Rs -{MONTHLY_LOSS_LIMIT:,.0f}",
        f"Month: {today.strftime('%b %Y')}",
        "",
        "Agent halted. Review your monthly trades, then run:",
        f"  del {MONTHLY_HALT_FLAG}",
        "Then restart the agent.",
    ])

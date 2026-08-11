"""
End-of-day email report — Phase 2.8

After the post-market EOD data download each trading day, the live agent calls
send_eod_email() to email a summary of the day's paper trades to your inbox.

Uses Gmail SMTP with an App Password. No extra dependencies — everything here is
Python standard library (smtplib / email / ssl) plus pandas, which is already used.

Configuration lives in .env and is fully parameterized (change any of it any time,
no code edits, no restart — values are re-read each time an email is sent):

  EMAIL_ENABLED        'true' to send the daily email; anything else = off
  EMAIL_FROM           Gmail address that SENDS the report
  EMAIL_APP_PASSWORD   16-char Gmail App Password (NOT your normal login password)
  EMAIL_TO             recipient(s); comma-separated for several
  EMAIL_SMTP_HOST      default smtp.gmail.com  (override only for a non-Gmail sender)
  EMAIL_SMTP_PORT      default 587 (STARTTLS); use 465 for implicit SSL

Getting a Gmail App Password (one-time, ~2 minutes):
  1. Turn on 2-Step Verification on the sending Google account.
  2. Google Account → Security → App passwords → generate one for "Mail".
  3. Paste the 16-character code into EMAIL_APP_PASSWORD in .env
     (spaces are fine — they're stripped automatically).

Manual test (send a report right now, without waiting for the 2:50 PM square-off):
  python live/email_report.py               # today, ignores EMAIL_ENABLED
  python live/email_report.py --date 2026-08-07   # re-send a past day
"""

import logging
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass, field
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path

# Allow running this file directly (`python live/email_report.py`): ensure the
# project root is importable so the `config` / `live` packages resolve, just as
# they do when the module is imported by the agent.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
from dotenv import load_dotenv

from config.settings import DAILY_LOSS_LIMIT, MONTHLY_LOSS_LIMIT, CHECKPOINT_DIR
from live.paper_logger import LIVE_TRADES_FILE

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_PATH     = _PROJECT_ROOT / ".env"
_LOG_DIR      = _PROJECT_ROOT / "logs"

load_dotenv(_ENV_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmailConfig:
    enabled:    bool
    sender:     str
    password:   str
    recipients: list[str] = field(default_factory=list)
    host:       str = "smtp.gmail.com"
    port:       int = 587

    def validate(self) -> tuple[bool, str]:
        """Return (ok, reason). reason explains what's missing when not ok."""
        if not self.sender:
            return False, "EMAIL_FROM is not set in .env"
        if not self.password:
            return False, "EMAIL_APP_PASSWORD is not set in .env (use a Gmail App Password)"
        if not self.recipients:
            return False, "EMAIL_TO is not set in .env"
        return True, ""


def _load_config() -> EmailConfig:
    """
    Read email settings fresh from .env every time (override=True) so edits to
    the from/to addresses take effect without restarting a day-long agent run.
    """
    load_dotenv(_ENV_PATH, override=True)

    enabled  = os.getenv("EMAIL_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
    sender   = os.getenv("EMAIL_FROM", "").strip()
    password = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    to_raw   = os.getenv("EMAIL_TO", "").strip()
    # Accept commas or semicolons between multiple recipients.
    recipients = [a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip()]
    host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    try:
        port = int(os.getenv("EMAIL_SMTP_PORT", "587").strip() or "587")
    except ValueError:
        port = 587

    return EmailConfig(enabled, sender, password, recipients, host, port)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers — read the day's trades from the live paper-trade log
# ─────────────────────────────────────────────────────────────────────────────

def _load_all_trades() -> pd.DataFrame:
    if not LIVE_TRADES_FILE.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(LIVE_TRADES_FILE, parse_dates=["date"])
    except Exception as e:
        log.warning(f"EOD email: could not read {LIVE_TRADES_FILE.name} — {e}")
        return pd.DataFrame()


def _today_trades(df: pd.DataFrame, today: date) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    return df[df["date"].dt.date == today].copy()


def _mtd_pnl(df: pd.DataFrame, today: date) -> float:
    if df.empty or "pnl_rs" not in df.columns:
        return 0.0
    month_start = today.replace(day=1)
    mask = (df["date"].dt.date >= month_start) & (df["date"].dt.date <= today)
    return float(df.loc[mask, "pnl_rs"].sum())


def _halt_flags() -> list[tuple[str, str]]:
    """Return active risk-halt flags as (label, reason) pairs (empty if none)."""
    flags = []
    for label, fp in (
        ("DAILY HALT",   CHECKPOINT_DIR / "HALT_DAILY.flag"),
        ("MONTHLY HALT", CHECKPOINT_DIR / "HALT_MONTHLY.flag"),
    ):
        if fp.exists():
            try:
                flags.append((label, fp.read_text().strip()))
            except Exception:
                flags.append((label, "(reason unreadable)"))
    return flags


def _rs(x: float) -> str:
    """Format a rupee amount with an explicit sign: 'Rs +1,585' / 'Rs -3,732'."""
    sign = "+" if x >= 0 else "-"
    return f"Rs {sign}{abs(x):,.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# Message building
# ─────────────────────────────────────────────────────────────────────────────

def _subject(today: date, tdf: pd.DataFrame, day_pnl: float) -> str:
    n = len(tdf)
    if n == 0:
        return f"[EOD Report] {today} — no trade"
    wins   = int((tdf["pnl_rs"] > 0).sum())
    losses = n - wins
    plural = "s" if n != 1 else ""
    return (f"[EOD Report] {today} — {_rs(day_pnl)} "
            f"({n} trade{plural}, {wins}W/{losses}L)")


def _eod_line(eod_result) -> str:
    if not isinstance(eod_result, dict):
        return "EOD data download: status unknown (see attached log)."
    completed = eod_result.get("completed", "?")
    failed    = eod_result.get("failed", "?")
    return f"EOD data download: {completed} stocks saved, {failed} failed."


def _text_body(today, tdf, day_pnl, mtd, eod_result, halts) -> str:
    lines = [
        f"EOD Report — {today}",
        "=" * 52,
        "",
    ]
    if tdf.empty:
        lines.append("No trade placed today (no signal passed all filters).")
    else:
        lines.append(f"Today's P&L : {_rs(day_pnl)}")
        for _, r in tdf.iterrows():
            lines.append(
                f"  {r['direction']:<5} {r['symbol']:<12} "
                f"entry {r.get('entry_time','')}@{r['entry_price']:.2f}  "
                f"exit {r.get('exit_time','')}@{r['exit_price']:.2f}  "
                f"{r['exit_reason']:<16} {r['result']:<9} "
                f"{_rs(r['pnl_rs'])} ({r['pnl_pct']:+.2f}%)"
            )
    lines += [
        "",
        f"MTD P&L     : {_rs(mtd)}  (monthly limit Rs -{MONTHLY_LOSS_LIMIT:,.0f})",
        f"Daily limit : Rs -{DAILY_LOSS_LIMIT:,.0f}",
        "",
        _eod_line(eod_result),
    ]
    if halts:
        lines += ["", "!! RISK HALT ACTIVE — agent will NOT trade tomorrow until cleared:"]
        for label, reason in halts:
            lines.append(f"   [{label}] {reason}")
    lines += ["", "— Paper mode (Phase 2.5). Full log attached."]
    return "\n".join(lines)


def _html_body(today, tdf, day_pnl, mtd, eod_result, halts) -> str:
    pnl_color = "#137333" if day_pnl >= 0 else "#c5221f"
    mtd_color = "#137333" if mtd >= 0 else "#c5221f"

    if tdf.empty:
        trades_html = (
            '<p style="margin:16px 0;color:#5f6368;">'
            "No trade placed today (no signal passed all filters).</p>"
        )
    else:
        rows = []
        for _, r in tdf.iterrows():
            win = r["pnl_rs"] > 0
            res_color = "#137333" if win else "#c5221f"
            dir_bg    = "#e6f4ea" if r["direction"] == "LONG" else "#fce8e6"
            dir_fg    = "#137333" if r["direction"] == "LONG" else "#c5221f"
            rows.append(f"""
              <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px 10px;font-weight:600;">{r['symbol']}</td>
                <td style="padding:8px 10px;">
                  <span style="background:{dir_bg};color:{dir_fg};padding:2px 8px;
                        border-radius:10px;font-size:12px;font-weight:600;">{r['direction']}</span>
                </td>
                <td style="padding:8px 10px;white-space:nowrap;">{r.get('entry_time','')} @ {r['entry_price']:.2f}</td>
                <td style="padding:8px 10px;white-space:nowrap;">{r.get('exit_time','')} @ {r['exit_price']:.2f}</td>
                <td style="padding:8px 10px;color:#5f6368;">{r['exit_reason']}</td>
                <td style="padding:8px 10px;font-weight:600;color:{res_color};">{r['result']}</td>
                <td style="padding:8px 10px;text-align:right;font-weight:600;color:{res_color};white-space:nowrap;">
                  {_rs(r['pnl_rs'])}<br><span style="font-weight:400;font-size:12px;">{r['pnl_pct']:+.2f}%</span>
                </td>
              </tr>""")
        trades_html = f"""
          <table style="border-collapse:collapse;width:100%;font-size:14px;margin-top:8px;">
            <thead>
              <tr style="background:#f1f3f4;text-align:left;color:#5f6368;font-size:12px;
                         text-transform:uppercase;letter-spacing:.3px;">
                <th style="padding:8px 10px;">Symbol</th>
                <th style="padding:8px 10px;">Dir</th>
                <th style="padding:8px 10px;">Entry</th>
                <th style="padding:8px 10px;">Exit</th>
                <th style="padding:8px 10px;">Reason</th>
                <th style="padding:8px 10px;">Result</th>
                <th style="padding:8px 10px;text-align:right;">P&amp;L</th>
              </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
          </table>"""

    halt_html = ""
    if halts:
        items = "".join(
            f'<li style="margin:4px 0;"><strong>{label}:</strong> {reason}</li>'
            for label, reason in halts
        )
        halt_html = f"""
          <div style="margin-top:20px;padding:12px 16px;background:#fce8e6;
                      border-left:4px solid #c5221f;border-radius:4px;">
            <div style="font-weight:700;color:#c5221f;">Risk halt active</div>
            <div style="color:#5f6368;font-size:13px;margin-top:4px;">
              The agent will NOT trade tomorrow until the flag is cleared.
            </div>
            <ul style="margin:8px 0 0;padding-left:20px;color:#3c4043;font-size:13px;">{items}</ul>
          </div>"""

    return f"""\
<!-- EOD report -->
<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
            max-width:720px;margin:0 auto;color:#202124;">
  <div style="border-bottom:2px solid #1a73e8;padding-bottom:12px;margin-bottom:16px;">
    <h2 style="margin:0;font-size:20px;">EOD Report</h2>
    <div style="color:#5f6368;font-size:14px;margin-top:2px;">{today} · Paper mode (Phase 2.5)</div>
  </div>

  <table style="border-collapse:collapse;width:100%;margin-bottom:8px;">
    <tr>
      <td style="padding:10px 14px;background:#f8f9fa;border-radius:8px;width:50%;">
        <div style="color:#5f6368;font-size:12px;text-transform:uppercase;">Today's P&amp;L</div>
        <div style="font-size:22px;font-weight:700;color:{pnl_color};margin-top:2px;">{_rs(day_pnl)}</div>
      </td>
      <td style="width:12px;"></td>
      <td style="padding:10px 14px;background:#f8f9fa;border-radius:8px;width:50%;">
        <div style="color:#5f6368;font-size:12px;text-transform:uppercase;">Month to date</div>
        <div style="font-size:22px;font-weight:700;color:{mtd_color};margin-top:2px;">{_rs(mtd)}</div>
      </td>
    </tr>
  </table>

  {trades_html}
  {halt_html}

  <p style="margin-top:20px;color:#5f6368;font-size:13px;">{_eod_line(eod_result)}</p>
  <p style="color:#9aa0a6;font-size:12px;border-top:1px solid #eee;padding-top:12px;margin-top:16px;">
    Daily loss limit Rs -{DAILY_LOSS_LIMIT:,.0f} · monthly limit Rs -{MONTHLY_LOSS_LIMIT:,.0f}.
    Full session log attached. Automated EOD report — paper mode.
  </p>
</div>"""


def _build_message(cfg: EmailConfig, today: date, all_df: pd.DataFrame, eod_result) -> MIMEMultipart:
    tdf     = _today_trades(all_df, today)
    day_pnl = float(tdf["pnl_rs"].sum()) if not tdf.empty else 0.0
    mtd     = _mtd_pnl(all_df, today)
    halts   = _halt_flags()

    msg = MIMEMultipart("mixed")
    msg["Subject"] = _subject(today, tdf, day_pnl)
    msg["From"]    = formataddr(("EOD Report", cfg.sender))
    msg["To"]      = ", ".join(cfg.recipients)
    msg["Date"]    = formatdate(localtime=True)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(_text_body(today, tdf, day_pnl, mtd, eod_result, halts), "plain", "utf-8"))
    alt.attach(MIMEText(_html_body(today, tdf, day_pnl, mtd, eod_result, halts), "html", "utf-8"))
    msg.attach(alt)

    # Attach today's session log (best-effort — never block the email on this).
    log_file = _LOG_DIR / f"live_{today}.log"
    if log_file.exists():
        try:
            part = MIMEApplication(log_file.read_bytes(), Name=log_file.name)
            part["Content-Disposition"] = f'attachment; filename="{log_file.name}"'
            msg.attach(part)
        except Exception as e:
            log.debug(f"EOD email: could not attach log ({log_file.name}) — {e}")

    return msg


def _deliver(cfg: EmailConfig, msg: MIMEMultipart) -> None:
    context = ssl.create_default_context()
    if cfg.port == 465:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30, context=context) as server:
            server.login(cfg.sender, cfg.password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(cfg.sender, cfg.password)
            server.send_message(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def send_eod_email(today: date | None = None, eod_result: dict | None = None,
                   force: bool = False) -> bool:
    """
    Build and send the end-of-day report email. Returns True on success.

    Never raises — any failure is logged and swallowed so the agent's shutdown
    sequence is never interrupted by a mail problem.

    Args:
        today:      trading day to report on (defaults to today()).
        eod_result: dict returned by download_eod ({'completed', 'failed'}), if any.
        force:      send even when EMAIL_ENABLED is not 'true' (used by the CLI test).
    """
    today = today or date.today()
    cfg = _load_config()

    if not cfg.enabled and not force:
        log.info("EOD email: disabled (set EMAIL_ENABLED='true' in .env to enable).")
        return False

    ok, why = cfg.validate()
    if not ok:
        log.warning(f"EOD email: not sent — {why}.")
        return False

    try:
        all_df = _load_all_trades()
        msg    = _build_message(cfg, today, all_df, eod_result)
        _deliver(cfg, msg)
        log.info(f"EOD email: sent to {', '.join(cfg.recipients)} via {cfg.host}:{cfg.port}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("EOD email: authentication failed. For Gmail, EMAIL_APP_PASSWORD "
                  "must be a 16-char App Password (not your login password), and "
                  "2-Step Verification must be enabled on the sending account.")
        return False
    except Exception as e:
        log.error(f"EOD email: failed to send — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI — manual test / re-send
# ─────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Send the EOD trading email for a given day (manual test / re-send)."
    )
    parser.add_argument("--date", help="Trading day as YYYY-MM-DD (default: today).")
    parser.add_argument("--respect-enabled", action="store_true",
                        help="Honour EMAIL_ENABLED instead of forcing a send.")
    args = parser.parse_args()

    day = date.fromisoformat(args.date) if args.date else date.today()
    ok  = send_eod_email(day, force=not args.respect_enabled)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    _cli()

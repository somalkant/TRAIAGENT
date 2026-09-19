"""
Parse the live agent's session logs into a table of entry decisions.

The live scan (live/live_engine.py) logs, every 5-min bar:
  - the top-3 candidates per direction with score / agreeing / PASS|FAIL reason
  - every candidate it walked past and WHY (drift gate, stop-viability gate, fill gate)
  - the SIGNAL it finally took (driver, signal_time, entry_time, entry, stop, target, RR, ...)
  - "no signal" when nothing qualified

Any candidate with a SKIP line had already PASSED the quality filters (the drift /
viability / fill gates run after passes_all_filters), so the first such candidate of the
day is the stock the system "wanted first" — the first-pass stock.

Log sources (synced from EC2 via S3 into logs/ec2/):
  startup_YYYY-MM-DD.log   2026-07-01 onward (Mumbai box)
  live_YYYY-MM-DD.log      2026-06-29/30 (old us-east-1 box, partly UTC timestamps)
June 15-26 logs no longer exist (that box was terminated).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

SYM = r"[A-Z0-9&\-]+"
_TS = re.compile(r"^(\d\d):(\d\d):(\d\d)\s+(INFO|WARNING|ERROR|DEBUG)\s+(.*)$")

_PATTERNS = {
    "TOP": re.compile(
        rf"^\[(?P<dir>LONG|SHORT)\] (?P<sym>{SYM}): score=(?P<score>[-\d.]+)"
        rf"(?: agreeing=(?P<agreeing>\d+) bars=(?P<bars>\d+) (?P<verdict>PASS|FAIL)(?: — (?P<reason>.*))?"
        rf"| — (?P<novalid>no valid signal))"),
    "SKIP_DRIFT": re.compile(
        rf"^(?P<sym>{SYM}) \[(?P<dir>LONG|SHORT)\]: SKIPPED — price moved (?P<drift>[+-]?[\d.]+)% unfavorable "
        rf"vs researched entry (?P<entry>[\d.]+) \(live (?P<live>[\d.]+)\)"),
    "SKIP_VIABILITY": re.compile(
        rf"^SKIP \[viability\] (?P<sym>{SYM}) \[(?P<dir>LONG|SHORT)\]: driver=(?P<driver>\S+) "
        rf"entry=(?P<entry>[\d.]+) stop=(?P<stop>[\d.]+) target=(?P<target>[\d.]+) RR=(?P<rr>[-\d.]+) "
        rf"\| stop (?P<stop_pct>[\d.]+)% = (?P<atr_ratio>[\d.]+)x ATR\((?P<atr>[\d.]+)%\)"),
    "SKIP_FILL": re.compile(rf"^SKIP \[fill\] (?P<sym>{SYM}) \[(?P<dir>LONG|SHORT)\]: (?P<reason>.*)$"),
    "FILL": re.compile(
        rf"^FILL \[(?P<dir>LONG|SHORT)\]: (?P<sym>{SYM}) crossed spread (?P<ltp>[\d.]+) -> (?P<fill>[\d.]+) "
        rf"\(slip (?P<slip>[\d.]+)%\)"),
    "SL_CAP": re.compile(
        rf"^SL CAP \[(?P<dir>LONG|SHORT)\]: (?P<sym>{SYM}) stop (?P<old_stop>[\d.]+) \((?P<old_pct>[\d.]+)%\) "
        rf"-> (?P<stop>[\d.]+)"),
    "SIGNAL": re.compile(
        rf"^SIGNAL \[(?P<dir>LONG|SHORT)\]: (?P<sym>{SYM}) \| driver=(?P<driver>\S+) \| "
        rf"signal_time=(?P<signal_time>[\d:]+) entry_time=(?P<entry_time>[\d:]+)(?: \(age=(?P<age>\d+)m\))? \| "
        rf"entry=(?P<entry>[\d.]+) \(drift=(?P<drift>[+-]?[\d.]+)%\) \| target=(?P<target>[\d.]+) "
        rf"stop=(?P<stop>[\d.]+) RR=(?P<rr>[-\d.]+) \| agreeing=(?P<agreeing>\d+) score=(?P<score>[\d.]+) "
        rf"pred=(?P<pred>[\d.]+)%"),
    "NO_SIGNAL": re.compile(r"^(?P<slot>\d\d:\d\d) — no signal for (?P<dirs>\S+)"),
}
_NUMERIC = {"score", "agreeing", "bars", "drift", "entry", "live", "stop", "target", "rr", "stop_pct",
            "atr_ratio", "atr", "ltp", "fill", "slip", "old_stop", "old_pct", "age", "pred"}


def _log_date(path: Path) -> date | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return date.fromisoformat(m.group(1)) if m else None


def _to_ist(h: int, m: int, s: int) -> tuple[int, int, int]:
    """The old us-east-1 box logged some sessions in UTC; market hours in UTC are 03:45-10:00."""
    if h < 8:                                   # 03:xx-07:xx can only be UTC during a session
        t = datetime(2000, 1, 1, h, m, s) + timedelta(hours=5, minutes=30)
        return t.hour, t.minute, t.second
    return h, m, s


def parse_log(path: Path) -> pd.DataFrame:
    d = _log_date(path)
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _TS.match(line.rstrip("\n"))
            if not m:
                continue
            h, mi, s = _to_ist(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if not (9 * 60 + 15 <= h * 60 + mi <= 15 * 60 + 30):
                continue
            msg = m.group(5).strip()
            for event, pat in _PATTERNS.items():
                pm = pat.match(msg)
                if not pm:
                    continue
                rec = {k: v for k, v in pm.groupdict().items() if v is not None}
                for k in list(rec):
                    if k in _NUMERIC:
                        try: rec[k] = float(rec[k])
                        except ValueError: pass
                rec.update(date=d, log_time=f"{h:02d}:{mi:02d}:{s:02d}", event=event,
                           # a scan is kicked off on the 5-min boundary and can take ~3 min to finish
                           scan_slot=f"{h:02d}:{(mi // 5) * 5:02d}")
                if event == "NO_SIGNAL":
                    rec["scan_slot"] = rec.pop("slot")
                rows.append(rec)
                break
    return pd.DataFrame(rows)


def load_decisions(log_dir: Path) -> pd.DataFrame:
    """All parsed decision events from every session log in log_dir, in time order."""
    files = sorted(log_dir.glob("startup_2026-*.log")) + sorted(log_dir.glob("live_2026-*.log"))
    by_day: dict[date, Path] = {}
    for f in files:                              # prefer startup_* when both exist for a day
        dd = _log_date(f)
        if dd and (dd not in by_day or f.name.startswith("startup_")):
            by_day[dd] = f
    frames = [parse_log(p) for _, p in sorted(by_day.items())]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["seq"] = range(len(df))
    return df


def first_pass_candidates(dec: pd.DataFrame, direction: str = "LONG") -> pd.DataFrame:
    """
    Per day: the first candidate that passed the quality filters (i.e. was walked to a
    drift / viability / fill gate, or was taken), with why it was or wasn't taken, and
    the trade actually taken that day.
    """
    gated = dec[(dec.get("dir") == direction) &
                dec.event.isin(["SKIP_DRIFT", "SKIP_VIABILITY", "SKIP_FILL", "SIGNAL"])].sort_values("seq")
    out = []
    for d, g in gated.groupby("date"):
        first = g.iloc[0]
        taken = g[g.event == "SIGNAL"]
        taken = taken.iloc[0] if len(taken) else None
        out.append({
            "date": d,
            "first_symbol": first["sym"], "first_event": first["event"], "first_slot": first["scan_slot"],
            "first_research_entry": first.get("entry"), "first_live_price": first.get("live"),
            "first_drift_pct": first.get("drift"),
            "n_skips_before_take": int((g.seq < (taken["seq"] if taken is not None else 10**12)).sum()
                                       - (0 if taken is None else 0)),
            "taken_symbol": None if taken is None else taken["sym"],
            "taken_slot": None if taken is None else taken["scan_slot"],
            "taken_driver": None if taken is None else taken.get("driver"),
            "first_was_taken": taken is not None and taken["seq"] == first["seq"],
        })
    return pd.DataFrame(out)

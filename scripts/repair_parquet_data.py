"""
Repair every stored 5-min bar file into the canonical format (data_pipeline/bars.py) and,
optionally, re-download days that are damaged beyond local repair.

What it fixes (found 2026-09-19, see notebooks/05):
  * tz-aware files (the Kite bulk history, and the 2026 index files) -> naive IST, so years can be
    concatenated (the backtester silently dropped all of 2026 because of the mix);
  * bars outside the 09:15-15:25 session -> removed: junk +5:30 copies left by the pre-07-21 append
    bug on 06-24 / 06-25 / 06-29 / 07-16, and pre-open / post-close bars the API returned on
    07-29 / 08-21 and a few other days;
  * duplicate timestamps -> one row.
What it can only DETECT locally (needs the broker API — run with --redownload on EC2):
  * days whose afternoon bars were overwritten by +5:30 copies of the morning (14:45-14:55 identical
    to 09:15-09:25), and session days with fewer than 70 bars.

Usage:
    python scripts/repair_parquet_data.py --dry-run            # report only (default years: all)
    python scripts/repair_parquet_data.py                      # rewrite files locally
    python scripts/repair_parquet_data.py --redownload --broker groww   # + re-fetch damaged days (EC2)

Writes reports/data_repair_<timestamp>.csv (one row per damaged symbol-day).
"""
from __future__ import annotations

import argparse
import sys
import time as time_mod
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.settings import STOCKS_DIR, INDEX_DIR, RATE_LIMIT_SLEEP   # noqa: E402
from data_pipeline.bars import normalize_bars, audit                  # noqa: E402

SHORT_DAY_BARS = 70
_INDEX_TOKENS = {"NIFTY50": 256265, "INDIAVIX": 264969}


def repair_file(path: Path, dry_run: bool) -> dict:
    raw = pd.read_parquet(path)
    a = audit(raw)
    fixed = normalize_bars(raw)
    per_day = fixed["datetime"].dt.date.value_counts()
    short = sorted(per_day[per_day < SHORT_DAY_BARS].index)
    changed = a["tz_aware"] or a["out_of_session"] or a["duplicates"]
    if changed and not dry_run:
        fixed.to_parquet(path, compression="snappy", index=False)
    return {"file": str(path.relative_to(ROOT)), "symbol": path.stem, "year": path.parent.name,
            "kind": "index" if INDEX_DIR in path.parents else "stock",
            "tz_aware": a["tz_aware"], "out_of_session": a["out_of_session"], "duplicates": a["duplicates"],
            "rows_before": len(raw), "rows_after": len(fixed),
            "corrupt_days": a["corrupt_afternoon_days"], "short_days": short}


def redownload(report: pd.DataFrame, broker_name: str, include_short: bool) -> pd.DataFrame:
    """Re-fetch damaged days from the broker and merge them (fresh rows replace stored rows)."""
    from brokers import get_broker
    from live.instrument_map import load_instrument_map
    from data_pipeline.downloader import _append_parquet

    class _Args:
        token = None
    import logging
    broker = get_broker(broker_name)
    Client, _ = broker.get_api_classes()
    broker.authenticate(logging.getLogger("repair"))      # refreshes the daily token (TOTP) if needed
    api_key, access = broker.get_credentials(_Args())
    kite = Client(api_key=api_key)
    kite.set_access_token(access)
    imap = load_instrument_map(kite, broker_name)

    out = []
    for r in report.itertuples():
        days = list(r.corrupt_days) + (list(r.short_days) if include_short else [])
        token = _INDEX_TOKENS.get(r.symbol) if r.kind == "index" else imap.get(r.symbol)
        for d in sorted(set(days)):
            status = "no_token"
            if token:
                try:
                    time_mod.sleep(RATE_LIMIT_SLEEP)
                    rows = kite.historical_data(instrument_token=int(token),
                                                from_date=datetime.combine(d, time(9, 15)),
                                                to_date=datetime.combine(d, time(15, 29)), interval="5minute")
                    if rows:
                        df = pd.DataFrame(rows).rename(columns={"date": "datetime"})
                        df["symbol"] = r.symbol
                        df = df[["datetime", "symbol", "open", "high", "low", "close", "volume"]]
                        before = len(normalize_bars(df))
                        _append_parquet(ROOT / r.file, df)
                        status = f"replaced ({before} session bars)"
                    else:
                        status = "api_returned_nothing"
                except Exception as e:
                    status = f"error: {type(e).__name__}: {e}"[:120]
            out.append({"symbol": r.symbol, "file": r.file, "day": d,
                        "reason": "corrupt_afternoon" if d in r.corrupt_days else "short_day", "status": status})
            print(f"  {r.symbol} {d}: {status}")
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="all", help="'all' or comma list, e.g. 2025,2026")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redownload", action="store_true", help="re-fetch damaged days via the broker API")
    ap.add_argument("--include-short-days", action="store_true", help="also re-fetch days with <70 bars")
    ap.add_argument("--broker", default="groww")
    a = ap.parse_args()

    years = (sorted({p.name for p in STOCKS_DIR.iterdir() if p.is_dir()} | {p.name for p in INDEX_DIR.iterdir() if p.is_dir()})
             if a.years == "all" else a.years.split(","))
    rows = []
    for y in years:
        for base in (STOCKS_DIR, INDEX_DIR):
            files = sorted((base / y).glob("*.parquet")) if (base / y).exists() else []
            for f in files:
                try:
                    rows.append(repair_file(f, a.dry_run))
                except Exception as e:
                    print(f"  {f}: ERROR {type(e).__name__}: {e}")
            if files:
                sub = [r for r in rows if r["year"] == y and r["kind"] == ("index" if base == INDEX_DIR else "stock")]
                print(f"{y} {'index' if base == INDEX_DIR else 'stocks'}: {len(files)} files | tz-aware {sum(r['tz_aware'] for r in sub)} | "
                      f"out-of-session bars {sum(r['out_of_session'] for r in sub):,} | duplicates {sum(r['duplicates'] for r in sub)} | "
                      f"corrupt afternoons {sum(len(r['corrupt_days']) for r in sub)} | short days {sum(len(r['short_days']) for r in sub)}")
    R = pd.DataFrame(rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (ROOT / "reports").mkdir(exist_ok=True)
    damaged = R[(R.corrupt_days.str.len() > 0) | (R.short_days.str.len() > 0)]
    damaged.to_csv(ROOT / "reports" / f"data_repair_{stamp}.csv", index=False)
    print(f"\n{'DRY RUN — nothing written. ' if a.dry_run else ''}{len(R)} files checked; "
          f"{int((R.tz_aware | (R.out_of_session > 0) | (R.duplicates > 0)).sum())} needed normalising. "
          f"Damaged symbol-days needing the API: {int(damaged.corrupt_days.str.len().sum())} corrupt afternoons, "
          f"{int(damaged.short_days.str.len().sum())} short days -> reports/data_repair_{stamp}.csv")
    if a.redownload and not a.dry_run and len(damaged):
        res = redownload(damaged, a.broker, a.include_short_days)
        res.to_csv(ROOT / "reports" / f"data_redownload_{stamp}.csv", index=False)
        print(f"re-download: {res.status.str.startswith('replaced').sum()}/{len(res)} days replaced")


if __name__ == "__main__":
    main()

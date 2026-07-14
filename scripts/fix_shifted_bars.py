"""
One-time repair for the +5:30 EOD timestamp-shift bug (see data_pipeline/downloader.py
_normalize_intraday_bars). Scans every stock's current-year parquet file, finds days
whose bars landed outside plausible market hours (09:00-15:35) that correct cleanly
when shifted back by 5h30m, and rewrites the file with the fix applied.

Going forward, EOD downloads are normalized automatically at download time — this
script only needs to run once to clean up files written before that guard existed.

Usage:
    python scripts/fix_shifted_bars.py                  # current year, all universe stocks
    python scripts/fix_shifted_bars.py --year 2026
    python scripts/fix_shifted_bars.py --dry-run         # report only, don't write
"""
import argparse
import sys
from datetime import date, time as dtime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import STOCKS_DIR


def fix_file(path: Path, dry_run: bool) -> int:
    df = pd.read_parquet(path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    shifted_days = 0
    for d in df["datetime"].dt.date.unique():
        mask = df["datetime"].dt.date == d
        day_times = df.loc[mask, "datetime"].dt.time
        if day_times.min() >= dtime(14, 0) and day_times.max() > dtime(15, 35):
            shifted = df.loc[mask, "datetime"] - timedelta(hours=5, minutes=30)
            if shifted.dt.time.min() >= dtime(9, 0) and shifted.dt.time.max() <= dtime(15, 35):
                df.loc[mask, "datetime"] = shifted
                shifted_days += 1
    if shifted_days and not dry_run:
        df = df.sort_values("datetime").drop_duplicates(subset=["datetime"]).reset_index(drop=True)
        df.to_parquet(path, compression="snappy", index=False)
    return shifted_days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    year_dir = STOCKS_DIR / str(args.year)
    if not year_dir.exists():
        print(f"No such directory: {year_dir}")
        return

    files = sorted(year_dir.glob("*.parquet"))
    print(f"Scanning {len(files)} files in {year_dir} ({'DRY RUN' if args.dry_run else 'WRITE'})...")

    total_fixed_files = 0
    total_fixed_days  = 0
    for f in files:
        try:
            n = fix_file(f, args.dry_run)
        except Exception as e:
            print(f"  {f.stem}: ERROR — {e}")
            continue
        if n:
            total_fixed_files += 1
            total_fixed_days  += n
            print(f"  {f.stem}: fixed {n} day(s)")

    print(f"\nDone. {total_fixed_files}/{len(files)} files had shifted days, "
          f"{total_fixed_days} day(s) corrected total.")
    if args.dry_run:
        print("(dry run — no files were written)")


if __name__ == "__main__":
    main()

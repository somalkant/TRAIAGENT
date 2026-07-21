"""
Repair for the +5:30 EOD timestamp-shift bug.

Root cause (confirmed 2026-07-21, reproduced directly): _append_parquet() used
to cast newly-downloaded (naive, IST wall-clock) rows to the EXISTING parquet
file's Arrow schema before concatenating. Older files carry a tz-AWARE schema
(FixedOffset(330)) inherited from the original Kite-sourced bulk historical
download; Groww's daily EOD downloader produces naive datetimes. Casting a
naive column onto a tz-aware schema doesn't just relabel it — Arrow
reinterprets the naive value as UTC and shifts it to the target offset,
silently adding +5:30 to every appended row. This reproduced on a row that
was ALREADY correctly timestamped (09:15), independent of any upstream
parsing issue — meaning every EOD append onto a tz-aware file was shifting
its own data, even after the 2026-07-16 per-day detection/correction guard
(_normalize_intraday_bars), which only touches the in-memory dataframe
*before* this cast, not the cast itself.

data_pipeline/downloader.py's _append_parquet() is now fixed to strip tz from
both sides before casting, so this can no longer recur. This script repairs
data written before that fix:

  1. Strips any tz-aware schema to naive (tz_localize(None) — preserves the
     wall-clock digits, which are correct; only the redundant/dangerous label
     is dropped).
  2. Re-runs the existing day-level shift detection/correction, in case any
     days are genuinely mistimed at the source (independent of the cast bug).

Covers both STOCKS_DIR and INDEX_DIR (the original script only checked
stocks — index files go through the same _append_parquet and were equally at
risk, just not reviewed before now).

Usage:
    python scripts/fix_shifted_bars.py                  # current year, stocks + index
    python scripts/fix_shifted_bars.py --year 2025
    python scripts/fix_shifted_bars.py --year all        # every year subdirectory found
    python scripts/fix_shifted_bars.py --dry-run         # report only, don't write
"""
import argparse
import sys
from datetime import date, time as dtime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import STOCKS_DIR, INDEX_DIR


def fix_file(path: Path, dry_run: bool) -> tuple[bool, int]:
    """Returns (tz_stripped, shifted_days_corrected)."""
    df = pd.read_parquet(path)
    df["datetime"] = pd.to_datetime(df["datetime"])

    tz_stripped = isinstance(df["datetime"].dtype, pd.DatetimeTZDtype)
    if tz_stripped:
        df["datetime"] = df["datetime"].dt.tz_localize(None)

    shifted_days = 0
    for d in df["datetime"].dt.date.unique():
        mask = df["datetime"].dt.date == d
        day_times = df.loc[mask, "datetime"].dt.time
        if day_times.min() >= dtime(14, 0) and day_times.max() > dtime(15, 35):
            shifted = df.loc[mask, "datetime"] - timedelta(hours=5, minutes=30)
            if shifted.dt.time.min() >= dtime(9, 0) and shifted.dt.time.max() <= dtime(15, 35):
                df.loc[mask, "datetime"] = shifted
                shifted_days += 1

    if (tz_stripped or shifted_days) and not dry_run:
        df = df.sort_values("datetime").drop_duplicates(subset=["datetime"]).reset_index(drop=True)
        df.to_parquet(path, compression="snappy", index=False)

    return tz_stripped, shifted_days


def scan_dir(dir_path: Path, label: str, dry_run: bool) -> tuple[int, int, int]:
    if not dir_path.exists():
        print(f"No such directory: {dir_path}")
        return 0, 0, 0

    files = sorted(dir_path.glob("*.parquet"))
    print(f"Scanning {len(files)} {label} files in {dir_path} ({'DRY RUN' if dry_run else 'WRITE'})...")

    tz_fixed_files = shifted_files = shifted_days_total = 0
    for f in files:
        try:
            tz_stripped, n_days = fix_file(f, dry_run)
        except Exception as e:
            print(f"  {f.stem}: ERROR — {e}")
            continue
        if tz_stripped:
            tz_fixed_files += 1
        if n_days:
            shifted_files += 1
            shifted_days_total += n_days
        if tz_stripped or n_days:
            tags = []
            if tz_stripped:
                tags.append("tz-aware schema -> naive")
            if n_days:
                tags.append(f"{n_days} shifted day(s) corrected")
            print(f"  {f.stem}: {', '.join(tags)}")

    return tz_fixed_files, shifted_files, shifted_days_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default=str(date.today().year),
                    help="year to scan, or 'all' for every year subdirectory found")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.year == "all":
        years = sorted({p.name for p in STOCKS_DIR.iterdir() if p.is_dir()}
                       | {p.name for p in INDEX_DIR.iterdir() if p.is_dir()})
    else:
        years = [args.year]

    grand_tz = grand_shift_files = grand_shift_days = 0
    for yr in years:
        tz1, sf1, sd1 = scan_dir(STOCKS_DIR / yr, f"stock ({yr})", args.dry_run)
        tz2, sf2, sd2 = scan_dir(INDEX_DIR  / yr, f"index ({yr})", args.dry_run)
        grand_tz          += tz1 + tz2
        grand_shift_files += sf1 + sf2
        grand_shift_days  += sd1 + sd2

    print(f"\nDone. {grand_tz} file(s) had a tz-aware schema stripped to naive; "
          f"{grand_shift_files} file(s) had {grand_shift_days} shifted day(s) corrected.")
    if args.dry_run:
        print("(dry run — no files were written)")


if __name__ == "__main__":
    main()

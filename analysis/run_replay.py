"""
Run analysis.replay over a date range in parallel, block by block (resumable).

    venv\\Scripts\\python.exe -m analysis.run_replay --start 2025-01-01 --end 2026-09-18 --workers 9

Writes reports/gap_analysis/replay/bt_<block>.parquet and cand_<block>.parquet; blocks already
on disk are skipped, so an interrupted run resumes where it stopped. Live-window days are
processed first so validation can start before the long history finishes.
"""
from __future__ import annotations

import argparse
import sys
import time as _time
from datetime import date, time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "reports" / "gap_analysis" / "replay"
LIVE_START, LIVE_END = date(2026, 6, 15), date(2026, 9, 18)


def _work(args):
    tag, days, last_scan = args
    import warnings; warnings.filterwarnings("ignore")
    from analysis import replay as R
    R.LAST_SCAN = last_scan
    t = _time.time()
    try:
        B, C = R.run_block(days, out_dir=OUT, tag=tag)
        return tag, len(days), len(B), len(C), _time.time() - t, None
    except Exception as e:                                   # keep the other blocks going
        import traceback
        return tag, len(days), 0, 0, _time.time() - t, traceback.format_exc()[-800:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-09-18")
    ap.add_argument("--workers", type=int, default=9)
    ap.add_argument("--block", type=int, default=8, help="trading days per block")
    ap.add_argument("--last-scan", default="11:30")
    a = ap.parse_args()

    from analysis import replay as R
    days = R.trading_days(date.fromisoformat(a.start), date.fromisoformat(a.end))
    h, m = map(int, a.last_scan.split(":"))
    blocks = [days[i:i + a.block] for i in range(0, len(days), a.block)]
    jobs = []
    for b in blocks:
        tag = f"{b[0]}_{b[-1]}"
        if (OUT / f"cand_{tag}.parquet").exists():
            continue
        jobs.append((tag, b, time(h, m)))
    jobs.sort(key=lambda j: not (j[1][-1] >= LIVE_START and j[1][0] <= LIVE_END))   # live window first
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{len(days)} trading days, {len(blocks)} blocks, {len(jobs)} to run, {a.workers} workers", flush=True)
    t0 = _time.time(); done = 0
    with Pool(a.workers, maxtasksperchild=1) as pool:
        for tag, nd, nb, nc, secs, err in pool.imap_unordered(_work, jobs):
            done += 1
            status = "ERROR" if err else "ok"
            print(f"[{done}/{len(jobs)}] {tag} {status} days={nd} bt={nb} cand={nc} {secs:.0f}s "
                  f"elapsed={(_time.time()-t0)/60:.1f}m", flush=True)
            if err:
                print(err, flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()

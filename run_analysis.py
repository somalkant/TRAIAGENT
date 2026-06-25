"""
Overnight analysis runner.

Usage:
    .\\venv\\Scripts\\python.exe run_analysis.py 2016
    .\\venv\\Scripts\\python.exe run_analysis.py 2017

Logs to logs/analysis_<year>.log
Resumes automatically from last checkpoint.
"""

import logging
import sys
from pathlib import Path

# ── prevent Windows sleep (no-op on Linux/Mac) ────────────────────────────────
def _keep_awake():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)

def _allow_sleep():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

# ── logging ───────────────────────────────────────────────────────────────────
def _setup_logging(year: int) -> Path:
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"analysis_{year}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return log_file


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python run_analysis.py <year>")
        print("  e.g: python run_analysis.py 2016")
        sys.exit(1)

    year = int(sys.argv[1])
    log_file = _setup_logging(year)

    log = logging.getLogger(__name__)
    log.info(f"=== Starting analysis for year {year} ===")
    log.info(f"Log file: {log_file}")

    # Prevent sleep BEFORE heavy work starts
    _keep_awake()
    log.info("Windows sleep prevention: ON")

    try:
        project_root = Path(__file__).parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from backtester.engine import run_year

        summary = run_year(year=year)

        log.info("=" * 50)
        log.info(f"YEAR {year} COMPLETE")
        log.info(f"Total trades : {summary['total_trades']}")
        log.info(f"Win rate     : {summary['effective_win_rate']}%  "
                 f"({summary['exact_win_rate']}% exact + profitable TIME_EXITs)")
        log.info(f"Total P&L    : Rs {summary['total_pnl']:,.0f}")
        log.info("Top 5 strategies by final weight:")
        def _wl(w): return w.get("long", 1.0) if isinstance(w, dict) else float(w)
        for k, v in sorted(summary["final_weights"].items(), key=lambda x: -_wl(x[1]))[:5]:
            wl = _wl(v)
            ws = v.get("short", 1.0) if isinstance(v, dict) else 1.0
            log.info(f"  {k:<15} long={wl:.3f}  short={ws:.3f}")
        log.info("=" * 50)

        # Save a dated weight snapshot so each training year can be rolled back to
        import shutil
        weights_src  = project_root / "checkpoints" / "strategy_weights.json"
        snapshot_dst = project_root / "checkpoints" / f"weights_after_{year}.json"
        if weights_src.exists():
            shutil.copy2(weights_src, snapshot_dst)
            log.info(f"Weight snapshot saved: {snapshot_dst.name}")

    except KeyboardInterrupt:
        log.info("Interrupted by user — checkpoint saved, safe to resume.")
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        _allow_sleep()
        log.info("Windows sleep prevention: OFF")


if __name__ == "__main__":
    main()

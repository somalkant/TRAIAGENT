"""
Walk-Forward Freeze Utility — Phase 2B

Run this after completing training for each WF boundary year to snapshot
the current weights before switching to test mode.

Usage (at the end of each WF training boundary):
    python scripts/wf_freeze.py --window 1   # after training 2016-2018
    python scripts/wf_freeze.py --window 2   # after training 2016-2019
    python scripts/wf_freeze.py --window 3   # after training 2016-2020
    python scripts/wf_freeze.py --window 4   # after training 2016-2021
    python scripts/wf_freeze.py --window 5   # after training 2016-2022 ← FINAL LIVE WEIGHTS

What it does:
  1. Copies checkpoints/strategy_weights.json → checkpoints/wf{N}_weights.json
  2. Appends an entry to checkpoints/wf_results.json with window metadata
  3. Prints a confirmation with the top-5 weights so you can visually verify

The frozen file wf{N}_weights.json is then used by:
    python run_testing.py <year> --wf-window N
"""

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR       = Path(__file__).parent.parent
CHECKPOINT_DIR = BASE_DIR / "checkpoints"
WEIGHTS_FILE   = CHECKPOINT_DIR / "strategy_weights.json"
WF_RESULTS_FILE = CHECKPOINT_DIR / "wf_results.json"

WF_SCHEDULE = {
    1: {"train": "2016-2018", "test": "2019",      "regime": "Late bull market"},
    2: {"train": "2016-2019", "test": "2020",      "regime": "COVID crash + V-recovery"},
    3: {"train": "2016-2020", "test": "2021",      "regime": "Strong momentum bull"},
    4: {"train": "2016-2021", "test": "2022",      "regime": "Sustained bear + high VIX"},
    5: {"train": "2016-2022", "test": "2023-2026", "regime": "Post-bear recovery + live period"},
    6: {"train": "2016-2024", "test": "2025-2026", "regime": "Post-recovery bull + rate cut cycle"},
}


def main():
    parser = argparse.ArgumentParser(
        description="Freeze WF weights snapshot at the end of a training boundary year."
    )
    parser.add_argument("--window", "-w", type=int, required=True, choices=[1, 2, 3, 4, 5, 6],
                        help="Walk-Forward window number (1-5)")
    args = parser.parse_args()

    n = args.window
    frozen_path = CHECKPOINT_DIR / f"wf{n}_weights.json"
    schedule    = WF_SCHEDULE[n]

    if not WEIGHTS_FILE.exists():
        print(f"ERROR: {WEIGHTS_FILE} not found. Run training before freezing.", file=sys.stderr)
        sys.exit(1)

    # 1. Copy current weights to frozen snapshot
    shutil.copy2(WEIGHTS_FILE, frozen_path)
    print(f"\n✓ WF-{n} weights frozen: {frozen_path}")

    # 2. Auto-update lifetime win rates from all prior completed WF test windows
    #    (WF-1 has no prior data, so this is a no-op for the first freeze)
    prior_windows = list(range(1, n))
    if prior_windows:
        print(f"\nRecomputing lifetime win rates from WF windows {prior_windows}...")
        logging.basicConfig(level=logging.INFO, format="  %(message)s")
        sys.path.insert(0, str(BASE_DIR))
        from backtester.winrate_updater import recompute_and_save
        recompute_and_save(prior_windows)
        print(f"✓ strategy_lifetime_winrates.json updated")
    else:
        print(f"\n(WF-1: no prior test data — lifetime win rates unchanged, using manual values)")

    # 3. Load the snapshot to show a summary
    with open(frozen_path) as f:
        weights = json.load(f)

    # Sort by long weight descending for display
    def long_w(w):
        return w.get("long", 1.0) if isinstance(w, dict) else float(w)

    top5 = sorted(weights.items(), key=lambda x: -long_w(x[1]))[:5]
    print(f"\nWF-{n} — Train: {schedule['train']} → Test: {schedule['test']}")
    print(f"Regime context: {schedule['regime']}")
    print(f"\nTop-5 long weights at freeze:")
    for name, w in top5:
        wl = w.get("long", 1.0)  if isinstance(w, dict) else float(w)
        ws = w.get("short", 1.0) if isinstance(w, dict) else 1.0
        print(f"  {name:<20} long={wl:.4f}  short={ws:.4f}")

    # 4. Append to wf_results.json
    results = {}
    if WF_RESULTS_FILE.exists():
        with open(WF_RESULTS_FILE) as f:
            results = json.load(f)

    results[f"WF-{n}"] = {
        "window":         n,
        "train_period":   schedule["train"],
        "test_period":    schedule["test"],
        "regime_context": schedule["regime"],
        "frozen_file":    str(frozen_path.name),
        "freeze_date":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "test_pnl":       None,    # filled in after running run_testing with --wf-window N
        "test_win_rate":  None,
        "test_trades":    None,
        "gate_pass":      None,
    }

    with open(WF_RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ wf_results.json updated (WF-{n} entry added, test results pending)")
    print(f"\nNext step:")
    print(f"  python run_testing.py {schedule['test'].split('-')[0]} --wf-window {n}")
    if n < max(WF_SCHEDULE):
        next_sched = WF_SCHEDULE[n + 1]
        next_train_year = next_sched["train"].split("-")[1]
        print(f"\nAfter testing, resume training:")
        print(f"  python run_analysis.py {next_train_year}")


if __name__ == "__main__":
    main()

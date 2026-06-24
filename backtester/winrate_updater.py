"""
Lifetime win rate updater — recomputes direction-specific win rates from WF perf files.

Called automatically by scripts/wf_freeze.py after each WF weight snapshot.
The updated strategy_lifetime_winrates.json is then used by the next WF test window.

Formula (same as effective_win_rate in strategy_agent.md tables):
  win_rate = sum(outcomes) / len(outcomes) * 100
    1.0 (TARGET_HIT)    = full credit
    0.5 (TIME_EXIT_WIN) = half credit  (trade profitable but target not reached)
    0.0 (LOSS)          = no credit

Update rule:
  - A direction's win rate is updated ONLY if >= min_signals outcomes exist.
  - Otherwise the existing JSON value is kept (preserves manual calibration).
  - This protects long win rates in a short-heavy system where long signals
    are rare (0-13 per WF window), while auto-updating short rates freely.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

BASE_DIR       = Path(__file__).parent.parent
CHECKPOINT_DIR = BASE_DIR / "checkpoints"
WR_FILE        = CHECKPOINT_DIR / "strategy_lifetime_winrates.json"

MIN_SIGNALS = 50


def recompute_and_save(
    completed_wf_windows: list[int],
    min_signals: int = MIN_SIGNALS,
) -> dict:
    """
    Recompute direction-specific lifetime win rates from completed WF test windows.

    completed_wf_windows: list of WF window numbers whose test years are done
                          e.g. [1, 2, 3] when freezing window 4

    Returns the updated {strategy: {"long": x, "short": y}} dict.
    """
    if not completed_wf_windows:
        log.info("No completed WF windows — lifetime win rates unchanged")
        return {}

    # ── Accumulate outcomes across all completed windows ─────────────────────
    long_outcomes:  dict[str, list] = {}
    short_outcomes: dict[str, list] = {}

    for wf_n in completed_wf_windows:
        long_path  = CHECKPOINT_DIR / f"wf{wf_n}_perf_long.json"
        short_path = CHECKPOINT_DIR / f"wf{wf_n}_perf_short.json"

        if long_path.exists():
            for strategy, outcomes in json.loads(long_path.read_text()).items():
                long_outcomes.setdefault(strategy, []).extend(outcomes)
        else:
            log.debug(f"  wf{wf_n}_perf_long.json not found — skipped")

        if short_path.exists():
            for strategy, outcomes in json.loads(short_path.read_text()).items():
                short_outcomes.setdefault(strategy, []).extend(outcomes)
        else:
            log.debug(f"  wf{wf_n}_perf_short.json not found — skipped")

    # ── Load existing JSON as baseline ────────────────────────────────────────
    raw_existing = {}
    if WR_FILE.exists():
        raw_existing = json.loads(WR_FILE.read_text())

    existing = {k: v for k, v in raw_existing.items() if not k.startswith("_")}

    # ── Recompute per strategy ────────────────────────────────────────────────
    all_strategies = sorted(set(existing) | set(long_outcomes) | set(short_outcomes))
    updated: dict[str, dict] = {}
    changed = 0

    for strategy in all_strategies:
        cur = existing.get(strategy, {})
        if isinstance(cur, dict):
            cur_long  = float(cur.get("long",  50.0))
            cur_short = float(cur.get("short", 50.0))
        else:
            cur_long  = float(cur) if cur else 50.0
            cur_short = 50.0

        # Long win rate
        l_outs = long_outcomes.get(strategy, [])
        if len(l_outs) >= min_signals:
            new_long = round(sum(l_outs) / len(l_outs) * 100, 1)
            if new_long != cur_long:
                log.info(f"  {strategy:<20} long : {cur_long:.1f}% -> {new_long:.1f}%  (n={len(l_outs)})")
                changed += 1
        else:
            new_long = cur_long
            if l_outs:
                log.debug(f"  {strategy:<20} long : kept {cur_long:.1f}%  (n={len(l_outs)} < {min_signals})")

        # Short win rate
        s_outs = short_outcomes.get(strategy, [])
        if len(s_outs) >= min_signals:
            new_short = round(sum(s_outs) / len(s_outs) * 100, 1)
            if new_short != cur_short:
                log.info(f"  {strategy:<20} short: {cur_short:.1f}% -> {new_short:.1f}%  (n={len(s_outs)})")
                changed += 1
        else:
            new_short = cur_short
            if s_outs:
                log.debug(f"  {strategy:<20} short: kept {cur_short:.1f}%  (n={len(s_outs)} < {min_signals})")

        updated[strategy] = {"long": new_long, "short": new_short}

    # ── Write back — preserve comment keys ───────────────────────────────────
    output = {k: v for k, v in raw_existing.items() if k.startswith("_")}
    output.update(updated)

    WR_FILE.write_text(json.dumps(output, indent=2))

    total_long  = sum(len(v) for v in long_outcomes.values())
    total_short = sum(len(v) for v in short_outcomes.values())
    log.info(
        f"strategy_lifetime_winrates.json updated — "
        f"WF windows {completed_wf_windows}, "
        f"{total_long} long / {total_short} short outcomes, "
        f"{changed} rates changed"
    )
    return updated

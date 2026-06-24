# Short WR Optimization — Experiment Log

## Files
- `winrates_v0_current.json` — baseline copy of strategy_lifetime_winrates.json

## Key finding
Short WRs in strategy_lifetime_winrates.json are correctly computed (WF2+WF3+WF4,
weighted formula: TARGET_HIT=1.0, TIME_EXIT_WIN=0.5, LOSS=0.0). WF2 has only 1 trade
per strategy but its 1% weight makes it a non-issue (max 0.2% impact).

## Root cause of FIRST-CANDLE dominance
NOT a WR calibration problem. Three reasons:
1. FIRST-CANDLE fires on nearly every stock every day (trivial trigger)
2. WR=65% × RR=2.0 = driver_score 1.30, highest among non-blocked strategies
3. The only higher-WR strategies (ORB-15 66.8%, ORB-30 69.8%) were already blocked

## Fix applied (2026-06-23)
Added FIRST-CANDLE to DRIVER_BLOCKED in backtester/engine.py.
It still votes on composite score but cannot set entries/targets.
Next driver candidates: PDH-PDL (68.8%), STOCHASTIC (69.8%), CAMARILLA (57.9%)

## Re-run 2023 to measure impact
```
.\venv\Scripts\python.exe run_testing.py 2023 --wf-window 5
```
Compare log vs logs/testing_2023_v0_baseline.log (back up first).
Watch which strategies now appear as driver= in the log.

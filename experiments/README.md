# Experiments

Each subfolder is one experiment. Run 2023 WF5 testing, save log, record summary here.

## Comparison Table

| Exp | DRIVER_BLOCKED additions | 2023 P&L | WR% | Trades | Top driver |
|-----|--------------------------|----------|-----|--------|------------|
| E00_baseline | (none beyond ORB/VOL/SR/REL) | ? | ? | 305 | FIRST-CANDLE (239/305=78%) |
| E01_fc_blocked | + FIRST-CANDLE | Rs 1,07,721 | 55.1% | 245 | varies (PDH-PDL/STOCH/MACD) — FAIL, rolled back |

Fill in after each run. Baseline log already saved as testing_2023_baseline.log.

## How to run an experiment

1. Make the config change (e.g. edit DRIVER_BLOCKED in engine.py)
2. Back up current log:  `copy logs\testing_2023.log experiments\E0X_name\testing_2023.log`
3. Delete old checkpoint so it re-runs from scratch:
   `del checkpoints\wf5_progress.json`
4. Run:  `.\venv\Scripts\python.exe run_testing.py 2023 --wf-window 5`
5. Copy new log into experiment folder, fill in table above
6. Revert or keep the config change for next experiment

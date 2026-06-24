# E01 — FIRST-CANDLE added to DRIVER_BLOCKED

## Config change vs E00
- DRIVER_BLOCKED: VOL-SPIKE, ORB-30, ORB-15, SR-BREAK, REL-STR, **FIRST-CANDLE**
- Everything else identical

## Rationale
FIRST-CANDLE drove 78% of 2023 SHORT trades due to:
1. Trivial trigger (fires on almost every stock every day)
2. Highest driver score among non-blocked strategies (WR=65% x RR=2.0 = 1.30)
Blocking forces PDH-PDL (WR=68.8%), STOCHASTIC (69.8%), CAMARILLA (57.9%) to drive.

## How to run
Delete wf5_progress.json first (so full 2023 re-runs from scratch):
```
del checkpoints\wf5_progress.json
.\venv\Scripts\python.exe run_testing.py 2023 --wf-window 5
```
Then copy log here:
```
copy logs\testing_2023.log experiments\E01_fc_blocked\testing_2023.log
```

## 2023 Results
- Trades: 245 (0 LONG, 245 SHORT)
- EXACT_WIN: 38 (15.5%)
- WIN partial: 97 (39.6%)
- LOSS: 110 (44.9%)
- Effective WR: 55.1%
- Total P&L: Rs 107,721

## Verdict: FAIL — rolled back
P&L dropped 73% vs baseline. EXACT_WIN halved (27.3% → 15.5%).
Replacement drivers (STOCHASTIC, PDH-PDL, MACD) set worse entries/targets.
FIRST-CANDLE's 65% WR is genuinely earned — not an artifact of selection bias.
FIRST-CANDLE removed from DRIVER_BLOCKED. Engine restored to E00 config.

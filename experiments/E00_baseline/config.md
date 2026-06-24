# E00 — Baseline (FIRST-CANDLE as driver, WF5 weights)

## Config
- DRIVER_BLOCKED: VOL-SPIKE, ORB-30, ORB-15, SR-BREAK, REL-STR
- WR file: strategy_lifetime_winrates.json (WF2+WF3+WF4 calibrated)
- Weights: wf5_weights.json

## 2023 Results (WF5)
- Trades: 245 (0 LONG, 245 SHORT)
- EXACT_WIN: 67 (27.3%)
- WIN partial: 93 (38.0%)
- LOSS: 85 (34.7%)
- Effective WR: 65.3%
- Total P&L: Rs 408,994

## Driver distribution
- FIRST-CANDLE: 239/305 trades = 78% in full 2023 log
  (WF5 portion: ~245 trades, dominated by FIRST-CANDLE)

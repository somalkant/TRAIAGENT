# Top-10 Strategy — Live Paper Trading Daily Log

Daily trade record for the live Top-10 correlation-reduced strategy agent (`live/top10_agent.py`).
Each strategy runs its own ₹10L (₹5L LONG pool / ₹5L SHORT pool, full-capital-deployed sizing),
max 1 LONG + 1 SHORT trade per strategy per day. Result labels: **EXACT_WIN** = target hit,
**WIN** = closed positive (time-exit or otherwise), **LOSS** = closed negative.

Source: `data/trade_logs/top10_live_trades.csv`. This file is appended to at the end of each
trading day — newest day at the bottom.

---

## 2026-07-15

### LONG

| Strategy | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|
| VPOC | AEGISLOG | 09:20 | 1263.61 | 395 | 13:24 | 1323.14 | TARGET_HIT | EXACT_WIN | +22,767.45 | +4.56% |
| REL-STR | AEGISLOG | 09:45 | 1291.30 | 387 | 14:00 | 1330.04 | TARGET_HIT | EXACT_WIN | +14,251.58 | +2.85% |
| RSI-EXT | HCLTECH | 09:20 | 1155.70 | 432 | 15:15 | 1167.90 | TIME_EXIT | WIN | +4,538.32 | +0.91% |
| INTRADAY-STRUCT | ATHERENERG | 10:15 | 1285.50 | 388 | 15:15 | 1297.00 | TIME_EXIT | WIN | +3,731.23 | +0.75% |
| ORB-15 | EICHERMOT | 09:40 | 7364.00 | 67 | 15:15 | 7408.50 | TIME_EXIT | WIN | +2,259.24 | +0.46% |
| VWAP-REV | POLYCAB | 10:10 | 9326.00 | 53 | 15:15 | 9339.50 | TIME_EXIT | LOSS | -6.17 | -0.00% |
| SUPERTREND | COFORGE | 09:25 | 1540.10 | 324 | 15:15 | 1532.70 | TIME_EXIT | LOSS | -3,123.24 | -0.63% |
| FAILED-BD | LT | 09:35 | 3851.50 | 129 | 12:14 | 3822.79 | STOP_HIT | LOSS | -4,425.26 | -0.89% |
| PIN-BAR | HEROMOTOCO | 09:35 | 4924.94 | 101 | 14:50 | 4874.93 | STOP_HIT | LOSS | -5,772.70 | -1.16% |

**LONG summary**: 9 trades — 2 EXACT_WIN, 3 WIN, 4 LOSS — net **+₹34,220.45** — avg P&L/trade **+0.76%**

### SHORT

| Strategy | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|
| ORB-15 | PATANJALI | 09:40 | 394.00 | 1269 | 10:38 | 364.90 | TARGET_HIT | EXACT_WIN | +36,220.12 | +7.24% |
| REL-STR | ADANIENSOL | 09:45 | 1695.10 | 294 | 15:15 | 1674.70 | TIME_EXIT | WIN | +5,274.36 | +1.06% |
| VPOC | ADANIENSOL | 09:20 | 1688.30 | 296 | 15:15 | 1674.70 | TIME_EXIT | WIN | +3,299.35 | +0.66% |
| SUPERTREND | TATACONSUM | 09:25 | 1092.20 | 457 | 15:15 | 1085.00 | TIME_EXIT | WIN | +2,562.75 | +0.51% |
| INTRADAY-STRUCT | AMBER | 10:15 | 7853.70 | 63 | 15:15 | 7841.50 | TIME_EXIT | WIN | +47.14 | +0.01% |
| PIN-BAR | FORCEMOT | 09:35 | 17804.00 | 28 | 10:01 | 17978.89 | STOP_HIT | LOSS | -5,626.49 | -1.13% |
| FAILED-BO | FORCEMOT | 09:35 | 17804.00 | 28 | 10:25 | 18032.71 | STOP_HIT | LOSS | -7,134.56 | -1.43% |
| RSI-EXT | ABB | 09:20 | 6973.73 | 71 | 10:59 | 7108.89 | STOP_HIT | LOSS | -10,323.95 | -2.09% |
| VWAP-REV | KALYANKJIL | 10:00 | 537.50 | 930 | 11:55 | 549.59 | STOP_HIT | LOSS | -11,982.36 | -2.40% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 4 WIN, 4 LOSS — net **+₹12,336.36** — avg P&L/trade **+0.27%**

### Day totals — 2026-07-15

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 3 | 7 | 8 | **+₹46,556.81** | **+0.52%** |

---

## 2026-07-16

Second live session — first day running with the fill-problem fix (pre-trade depth gate,
SHORT-side turnover floor, wider fill tolerance). All 18 trades cleared ≥50% fill; the gate
skipped 14 thin candidates and fell through to the next one instead of committing blind.

### LONG

| Strategy | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | AEGISLOG | 09:45 | 1291.00 | 387 | 15:14 | 1313.02 | TARGET_HIT | EXACT_WIN | +7,786.14 | +1.56% |
| RSI-EXT | POWERINDIA | 09:20 | 33080.00 | 15 | 15:15 | 33480.00 | TIME_EXIT | WIN | +5,271.52 | +1.06% |
| ORB-15 | ITC | 09:50 | 277.55 | 1801 | 15:15 | 279.30 | TIME_EXIT | WIN | +2,420.53 | +0.48% |
| REL-STR | BAJFINANCE | 09:45 | 1033.70 | 483 | 15:15 | 1037.00 | TIME_EXIT | WIN | +864.71 | +0.17% |
| SUPERTREND | HEROMOTOCO | 09:25 | 4906.40 | 101 | 15:15 | 4899.50 | TIME_EXIT | LOSS | -1,419.49 | -0.29% |
| VPOC | ITC | 09:20 | 277.36 | 1802 | 09:33 | 276.70 | STOP_HIT | LOSS | -1,919.22 | -0.38% |
| PIN-BAR | BHARTIARTL | 09:35 | 1927.20 | 259 | 15:15 | 1920.60 | TIME_EXIT | LOSS | -2,435.79 | -0.49% |
| INTRADAY-STRUCT | HINDUNILVR | 10:15 | 2115.00 | 236 | 13:43 | 2103.67 | STOP_HIT | LOSS | -3,399.50 | -0.68% |
| FAILED-BD | BSE | 09:35 | 3745.40 | 133 | 10:32 | 3706.77 | STOP_HIT | LOSS | -5,859.70 | -1.18% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 3 WIN, 5 LOSS — net **+₹1,309.20** — avg P&L/trade **+0.03%**

### SHORT

| Strategy | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | SWIGGY | 10:20 | 280.52 | 1782 | 14:11 | 276.22 | TARGET_HIT | EXACT_WIN | +6,940.27 | +1.39% |
| RSI-EXT | DIXON | 09:20 | 14634.00 | 34 | 09:48 | 14194.98 | TARGET_HIT | EXACT_WIN | +14,209.64 | +2.86% |
| ORB-15 | NATIONALUM | 09:45 | 359.40 | 1391 | 15:15 | 353.90 | TIME_EXIT | WIN | +6,926.07 | +1.39% |
| INTRADAY-STRUCT | HDFCBANK | 10:15 | 812.25 | 615 | 10:26 | 810.50 | TARGET_HIT | EXACT_WIN | +348.59 | +0.07% |
| FAILED-BO | BAJAJ-AUTO | 09:35 | 10361.00 | 48 | 15:15 | 10330.00 | TIME_EXIT | WIN | +763.58 | +0.15% |
| PIN-BAR | BANKBARODA | 09:35 | 248.30 | 2013 | 15:15 | 248.40 | TIME_EXIT | LOSS | -930.09 | -0.19% |
| VPOC | BANKBARODA | 09:20 | 248.30 | 2013 | 11:02 | 249.54 | STOP_HIT | LOSS | -3,229.24 | -0.65% |
| REL-STR | ADANIGREEN | 09:45 | 1551.00 | 322 | 10:39 | 1574.26 | STOP_HIT | LOSS | -8,223.73 | -1.65% |
| SUPERTREND | BHEL | 09:35 | 414.60 | 1205 | 14:19 | 424.50 | STOP_HIT | LOSS | -12,668.75 | -2.54% |

**SHORT summary**: 9 trades — 3 EXACT_WIN, 2 WIN, 4 LOSS — net **+₹4,136.34** — avg P&L/trade **+0.09%**

### Day totals — 2026-07-16

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 4 | 5 | 9 | **+₹5,445.54** | **+0.06%** |

**Known caveat on 2026-07-16 figures**: a bug found the same day means the actual verified fill
price (from the pre-trade depth gate) isn't propagated into P&L for trades that filled immediately
at the gate — only for the one trade that settled a bar later. True P&L for 2026-07-16, recomputed
against the real fill prices, was **+₹8,252.37** (vs +₹5,445.54 logged) — not yet corrected in the
source CSV or this table. Fix pending.

**Exit-fill verification added 2026-07-17**: exits (`TARGET_HIT`/`STOP_HIT`/`TIME_EXIT`) now run
the same depth-check the entry side already had — closing a LONG checks the bid book (need buyers
to sell to), closing a SHORT checks the ask book (need sellers to buy back from). The CSV gained
two columns, `exit_qty_filled` / `exit_fill_pct`, and the log shows `SOLD X/Y` or `BOUGHT X/Y` at
every exit. The 36 trades from 2026-07-15/16 predate this feature — their `exit_qty_filled` is
backfilled as a 100%-assumed, **unverified** placeholder, not a real measurement. From 2026-07-17
onward the figures are real.

---

## 2026-07-17

Third live session — first day with real (not backfilled) exit-fill verification. All 18 exits
closed at 100% fill, no penalty on any of them — the depth checks confirmed clean.

### LONG

| Strategy | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | AEGISLOG | 11:15 | 1296.90 | 385 | 12:53 | 1323.93 | TARGET_HIT | EXACT_WIN | +9,670.70 | +1.94% |
| VPOC | AXISBANK | 09:20 | 1308.60 | 382 | 09:32 | 1317.08 | TARGET_HIT | EXACT_WIN | +2,508.48 | +0.50% |
| FAILED-BD | BEL | 09:35 | 407.85 | 1225 | 15:15 | 409.40 | TIME_EXIT | WIN | +1,168.11 | +0.23% |
| PIN-BAR | BEL | 09:35 | 407.85 | 1225 | 15:15 | 409.40 | TIME_EXIT | WIN | +1,168.11 | +0.23% |
| INTRADAY-STRUCT | HINDUNILVR | 10:15 | 2134.70 | 234 | 12:42 | 2142.14 | TARGET_HIT | EXACT_WIN | +1,011.17 | +0.20% |
| SUPERTREND | ONGC | 09:25 | 247.33 | 2021 | 15:15 | 247.23 | TIME_EXIT | LOSS | -932.15 | -0.19% |
| RSI-EXT | ADANIGREEN | 09:20 | 1528.10 | 327 | 15:15 | 1515.00 | TIME_EXIT | LOSS | -5,008.79 | -1.00% |
| REL-STR | ADANIENSOL | 09:45 | 1741.30 | 287 | 15:15 | 1722.01 | TIME_EXIT | LOSS | -6,260.89 | -1.25% |
| ORB-15 | ADANIGREEN | 09:40 | 1548.80 | 322 | 10:43 | 1525.84 | STOP_HIT | LOSS | -8,115.40 | -1.63% |

**LONG summary**: 9 trades — 3 EXACT_WIN, 2 WIN, 4 LOSS — net **-₹4,790.66** — avg P&L/trade **-0.11%**

### SHORT

| Strategy | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|
| REL-STR | ADANIGREEN | 09:45 | 1544.70 | 323 | 15:15 | 1515.53 | TIME_EXIT | WIN | +8,699.82 | +1.74% |
| VPOC | COFORGE | 09:20 | 1550.22 | 322 | 09:44 | 1532.88 | TARGET_HIT | EXACT_WIN | +4,858.11 | +0.97% |
| PIN-BAR | BHARTIARTL | 09:35 | 1918.30 | 260 | 15:15 | 1909.50 | TIME_EXIT | WIN | +1,562.09 | +0.31% |
| ORB-15 | CANBK | 11:15 | 125.28 | 3991 | 15:15 | 125.11 | TIME_EXIT | LOSS | -50.04 | -0.01% |
| VWAP-REV | SWIGGY | 11:45 | 276.65 | 1807 | 15:15 | 277.22 | TIME_EXIT | LOSS | -1,770.61 | -0.35% |
| RSI-EXT | BAJAJ-AUTO | 09:20 | 10413.00 | 48 | 15:15 | 10446.50 | TIME_EXIT | LOSS | -2,337.59 | -0.47% |
| FAILED-BO | RELIANCE | 09:35 | 1309.00 | 381 | 09:43 | 1317.10 | STOP_HIT | LOSS | -3,815.04 | -0.76% |
| INTRADAY-STRUCT | BAJFINANCE | 10:15 | 1045.90 | 478 | 10:18 | 1052.43 | STOP_HIT | LOSS | -3,850.11 | -0.77% |
| SUPERTREND | ITC | 09:25 | 278.35 | 1796 | 10:17 | 280.80 | STOP_HIT | LOSS | -5,131.51 | -1.03% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 2 WIN, 6 LOSS — net **-₹1,834.88** — avg P&L/trade **-0.04%**

### Day totals — 2026-07-17

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 4 | 4 | 10 | **-₹6,625.54** | **-0.07%** |

Note: `FAILED-BD` and `PIN-BAR` both landed on the exact same trade today (LONG BEL, identical entry/exit) —
two independent strategies picked the same stock/direction/timing, each with their own ₹5L pool. Coincidence
worth watching for if it recurs, given the earlier finding that overlapping strategy picks compound demand
on the same book.

---

## Running totals (all days)

| Date | Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|---|
| 2026-07-15 | 18 | 3 | 7 | 8 | +₹46,556.81 | +0.52% |
| 2026-07-16 | 18 | 4 | 5 | 9 | +₹5,445.54 | +0.06% |
| 2026-07-17 | 18 | 4 | 4 | 10 | -₹6,625.54 | -0.07% |
| **Total** | **54** | **11** | **16** | **27** | **+₹45,376.81** | **+0.17%** |

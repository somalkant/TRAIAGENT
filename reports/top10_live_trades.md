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

| Strategy | Type | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VPOC | Indicator | AEGISLOG | 09:20 | 1263.61 | 395 | 13:24 | 1323.14 | TARGET_HIT | EXACT_WIN | +22,767.45 | +4.56% |
| REL-STR | Indicator | AEGISLOG | 09:45 | 1291.30 | 387 | 14:00 | 1330.04 | TARGET_HIT | EXACT_WIN | +14,251.58 | +2.85% |
| RSI-EXT | Indicator | HCLTECH | 09:20 | 1155.70 | 432 | 15:15 | 1167.90 | TIME_EXIT | WIN | +4,538.32 | +0.91% |
| INTRADAY-STRUCT | Price Action | ATHERENERG | 10:15 | 1285.50 | 388 | 15:15 | 1297.00 | TIME_EXIT | WIN | +3,731.23 | +0.75% |
| ORB-15 | Price Action | EICHERMOT | 09:40 | 7364.00 | 67 | 15:15 | 7408.50 | TIME_EXIT | WIN | +2,259.24 | +0.46% |
| VWAP-REV | Indicator | POLYCAB | 10:10 | 9326.00 | 53 | 15:15 | 9339.50 | TIME_EXIT | LOSS | -6.17 | -0.00% |
| SUPERTREND | Indicator | COFORGE | 09:25 | 1540.10 | 324 | 15:15 | 1532.70 | TIME_EXIT | LOSS | -3,123.24 | -0.63% |
| FAILED-BD | Price Action | LT | 09:35 | 3851.50 | 129 | 12:14 | 3822.79 | STOP_HIT | LOSS | -4,425.26 | -0.89% |
| PIN-BAR | Price Action | HEROMOTOCO | 09:35 | 4924.94 | 101 | 14:50 | 4874.93 | STOP_HIT | LOSS | -5,772.70 | -1.16% |

**LONG summary**: 9 trades — 2 EXACT_WIN, 3 WIN, 4 LOSS — net **+₹34,220.45** — avg P&L/trade **+0.76%**

### SHORT

| Strategy | Type | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-15 | Price Action | PATANJALI | 09:40 | 394.00 | 1269 | 10:38 | 364.90 | TARGET_HIT | EXACT_WIN | +36,220.12 | +7.24% |
| REL-STR | Indicator | ADANIENSOL | 09:45 | 1695.10 | 294 | 15:15 | 1674.70 | TIME_EXIT | WIN | +5,274.36 | +1.06% |
| VPOC | Indicator | ADANIENSOL | 09:20 | 1688.30 | 296 | 15:15 | 1674.70 | TIME_EXIT | WIN | +3,299.35 | +0.66% |
| SUPERTREND | Indicator | TATACONSUM | 09:25 | 1092.20 | 457 | 15:15 | 1085.00 | TIME_EXIT | WIN | +2,562.75 | +0.51% |
| INTRADAY-STRUCT | Price Action | AMBER | 10:15 | 7853.70 | 63 | 15:15 | 7841.50 | TIME_EXIT | WIN | +47.14 | +0.01% |
| PIN-BAR | Price Action | FORCEMOT | 09:35 | 17804.00 | 28 | 10:01 | 17978.89 | STOP_HIT | LOSS | -5,626.49 | -1.13% |
| FAILED-BO | Price Action | FORCEMOT | 09:35 | 17804.00 | 28 | 10:25 | 18032.71 | STOP_HIT | LOSS | -7,134.56 | -1.43% |
| RSI-EXT | Indicator | ABB | 09:20 | 6973.73 | 71 | 10:59 | 7108.89 | STOP_HIT | LOSS | -10,323.95 | -2.09% |
| VWAP-REV | Indicator | KALYANKJIL | 10:00 | 537.50 | 930 | 11:55 | 549.59 | STOP_HIT | LOSS | -11,982.36 | -2.40% |

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

| Strategy | Type | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | Indicator | AEGISLOG | 09:45 | 1291.00 | 387 | 15:14 | 1313.02 | TARGET_HIT | EXACT_WIN | +7,786.14 | +1.56% |
| RSI-EXT | Indicator | POWERINDIA | 09:20 | 33080.00 | 15 | 15:15 | 33480.00 | TIME_EXIT | WIN | +5,271.52 | +1.06% |
| ORB-15 | Price Action | ITC | 09:50 | 277.55 | 1801 | 15:15 | 279.30 | TIME_EXIT | WIN | +2,420.53 | +0.48% |
| REL-STR | Indicator | BAJFINANCE | 09:45 | 1033.70 | 483 | 15:15 | 1037.00 | TIME_EXIT | WIN | +864.71 | +0.17% |
| SUPERTREND | Indicator | HEROMOTOCO | 09:25 | 4906.40 | 101 | 15:15 | 4899.50 | TIME_EXIT | LOSS | -1,419.49 | -0.29% |
| VPOC | Indicator | ITC | 09:20 | 277.36 | 1802 | 09:33 | 276.70 | STOP_HIT | LOSS | -1,919.22 | -0.38% |
| PIN-BAR | Price Action | BHARTIARTL | 09:35 | 1927.20 | 259 | 15:15 | 1920.60 | TIME_EXIT | LOSS | -2,435.79 | -0.49% |
| INTRADAY-STRUCT | Price Action | HINDUNILVR | 10:15 | 2115.00 | 236 | 13:43 | 2103.67 | STOP_HIT | LOSS | -3,399.50 | -0.68% |
| FAILED-BD | Price Action | BSE | 09:35 | 3745.40 | 133 | 10:32 | 3706.77 | STOP_HIT | LOSS | -5,859.70 | -1.18% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 3 WIN, 5 LOSS — net **+₹1,309.20** — avg P&L/trade **+0.03%**

### SHORT

| Strategy | Type | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | Indicator | SWIGGY | 10:20 | 280.52 | 1782 | 14:11 | 276.22 | TARGET_HIT | EXACT_WIN | +6,940.27 | +1.39% |
| RSI-EXT | Indicator | DIXON | 09:20 | 14634.00 | 34 | 09:48 | 14194.98 | TARGET_HIT | EXACT_WIN | +14,209.64 | +2.86% |
| ORB-15 | Price Action | NATIONALUM | 09:45 | 359.40 | 1391 | 15:15 | 353.90 | TIME_EXIT | WIN | +6,926.07 | +1.39% |
| INTRADAY-STRUCT | Price Action | HDFCBANK | 10:15 | 812.25 | 615 | 10:26 | 810.50 | TARGET_HIT | EXACT_WIN | +348.59 | +0.07% |
| FAILED-BO | Price Action | BAJAJ-AUTO | 09:35 | 10361.00 | 48 | 15:15 | 10330.00 | TIME_EXIT | WIN | +763.58 | +0.15% |
| PIN-BAR | Price Action | BANKBARODA | 09:35 | 248.30 | 2013 | 15:15 | 248.40 | TIME_EXIT | LOSS | -930.09 | -0.19% |
| VPOC | Indicator | BANKBARODA | 09:20 | 248.30 | 2013 | 11:02 | 249.54 | STOP_HIT | LOSS | -3,229.24 | -0.65% |
| REL-STR | Indicator | ADANIGREEN | 09:45 | 1551.00 | 322 | 10:39 | 1574.26 | STOP_HIT | LOSS | -8,223.73 | -1.65% |
| SUPERTREND | Indicator | BHEL | 09:35 | 414.60 | 1205 | 14:19 | 424.50 | STOP_HIT | LOSS | -12,668.75 | -2.54% |

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

| Strategy | Type | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | Indicator | AEGISLOG | 11:15 | 1296.90 | 385 | 12:53 | 1323.93 | TARGET_HIT | EXACT_WIN | +9,670.70 | +1.94% |
| VPOC | Indicator | AXISBANK | 09:20 | 1308.60 | 382 | 09:32 | 1317.08 | TARGET_HIT | EXACT_WIN | +2,508.48 | +0.50% |
| FAILED-BD | Price Action | BEL | 09:35 | 407.85 | 1225 | 15:15 | 409.40 | TIME_EXIT | WIN | +1,168.11 | +0.23% |
| PIN-BAR | Price Action | BEL | 09:35 | 407.85 | 1225 | 15:15 | 409.40 | TIME_EXIT | WIN | +1,168.11 | +0.23% |
| INTRADAY-STRUCT | Price Action | HINDUNILVR | 10:15 | 2134.70 | 234 | 12:42 | 2142.14 | TARGET_HIT | EXACT_WIN | +1,011.17 | +0.20% |
| SUPERTREND | Indicator | ONGC | 09:25 | 247.33 | 2021 | 15:15 | 247.23 | TIME_EXIT | LOSS | -932.15 | -0.19% |
| RSI-EXT | Indicator | ADANIGREEN | 09:20 | 1528.10 | 327 | 15:15 | 1515.00 | TIME_EXIT | LOSS | -5,008.79 | -1.00% |
| REL-STR | Indicator | ADANIENSOL | 09:45 | 1741.30 | 287 | 15:15 | 1722.01 | TIME_EXIT | LOSS | -6,260.89 | -1.25% |
| ORB-15 | Price Action | ADANIGREEN | 09:40 | 1548.80 | 322 | 10:43 | 1525.84 | STOP_HIT | LOSS | -8,115.40 | -1.63% |

**LONG summary**: 9 trades — 3 EXACT_WIN, 2 WIN, 4 LOSS — net **-₹4,790.66** — avg P&L/trade **-0.11%**

### SHORT

| Strategy | Type | Symbol | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| REL-STR | Indicator | ADANIGREEN | 09:45 | 1544.70 | 323 | 15:15 | 1515.53 | TIME_EXIT | WIN | +8,699.82 | +1.74% |
| VPOC | Indicator | COFORGE | 09:20 | 1550.22 | 322 | 09:44 | 1532.88 | TARGET_HIT | EXACT_WIN | +4,858.11 | +0.97% |
| PIN-BAR | Price Action | BHARTIARTL | 09:35 | 1918.30 | 260 | 15:15 | 1909.50 | TIME_EXIT | WIN | +1,562.09 | +0.31% |
| ORB-15 | Price Action | CANBK | 11:15 | 125.28 | 3991 | 15:15 | 125.11 | TIME_EXIT | LOSS | -50.04 | -0.01% |
| VWAP-REV | Indicator | SWIGGY | 11:45 | 276.65 | 1807 | 15:15 | 277.22 | TIME_EXIT | LOSS | -1,770.61 | -0.35% |
| RSI-EXT | Indicator | BAJAJ-AUTO | 09:20 | 10413.00 | 48 | 15:15 | 10446.50 | TIME_EXIT | LOSS | -2,337.59 | -0.47% |
| FAILED-BO | Price Action | RELIANCE | 09:35 | 1309.00 | 381 | 09:43 | 1317.10 | STOP_HIT | LOSS | -3,815.04 | -0.76% |
| INTRADAY-STRUCT | Price Action | BAJFINANCE | 10:15 | 1045.90 | 478 | 10:18 | 1052.43 | STOP_HIT | LOSS | -3,850.11 | -0.77% |
| SUPERTREND | Indicator | ITC | 09:25 | 278.35 | 1796 | 10:17 | 280.80 | STOP_HIT | LOSS | -5,131.51 | -1.03% |

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

## 2026-07-20

Fourth live session — first day running with cross-strategy `(symbol, side)` exclusivity and the
new **move-strength** classification (STRONG/MEDIUM/LOW/UNRATED, computed at signal time before the
trade is placed — purely observational, does not affect sizing or entry/exit). Exclusivity fired 3
times today (`FAILED-BD`→CGPOWER LONG, `PIN-BAR`→LT SHORT, `ORB-15`→BEL SHORT all skipped and fell
through to their next candidate because another strategy already held that side of that stock) —
zero fill voids, zero incomplete exits. A rough day overall: 12 of 18 trades closed LOSS.

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | Indicator | ATHERENERG | MEDIUM | 09:50 | 1278.51 | 391 | 14:03 | 1301.89 | TARGET_HIT | EXACT_WIN | +8,405.59 | +1.68% |
| PIN-BAR | Price Action | ETERNAL | LOW | 09:35 | 285.95 | 1748 | 10:35 | 288.45 | TARGET_HIT | EXACT_WIN | +3,637.85 | +0.73% |
| SUPERTREND | Indicator | CGPOWER | MEDIUM | 09:25 | 906.60 | 551 | 15:15 | 911.50 | TIME_EXIT | WIN | +1,966.73 | +0.39% |
| ORB-15 | Price Action | BAJAJ-AUTO | STRONG | 09:40 | 10481.00 | 47 | 15:15 | 10519.76 | TIME_EXIT | WIN | +1,101.23 | +0.22% |
| VPOC | Indicator | HINDALCO | MEDIUM | 09:20 | 949.90 | 526 | 09:47 | 951.22 | TARGET_HIT | EXACT_WIN | -36.13 | -0.01% |
| INTRADAY-STRUCT | Price Action | ADANIENSOL | MEDIUM | 10:15 | 1732.80 | 288 | 10:58 | 1722.00 | STOP_HIT | LOSS | -3,835.55 | -0.77% |
| FAILED-BD | Price Action | INFY | LOW | 09:35 | 1097.60 | 455 | 12:14 | 1085.23 | STOP_HIT | LOSS | -6,351.65 | -1.27% |
| RSI-EXT | Indicator | AXISBANK | STRONG | 09:20 | 1271.40 | 393 | 15:15 | 1255.70 | TIME_EXIT | LOSS | -6,893.66 | -1.38% |
| REL-STR | Indicator | AEGISLOG | STRONG | 09:45 | 1426.00 | 350 | 11:02 | 1405.00 | STOP_HIT | LOSS | -8,071.86 | -1.62% |

**LONG summary**: 9 trades — 3 EXACT_WIN, 2 WIN, 4 LOSS — net **-₹10,077.45** — avg P&L/trade **-0.23%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VPOC | Indicator | COFORGE | STRONG | 09:25 | 1513.20 | 330 | 09:25 | 1507.39 | TARGET_HIT | EXACT_WIN | +1,190.66 | +0.24% |
| VWAP-REV | Indicator | BAJFINANCE | MEDIUM | 13:25 | 1064.50 | 469 | 15:15 | 1063.95 | TIME_EXIT | LOSS | -470.24 | -0.09% |
| SUPERTREND | Indicator | BEL | MEDIUM | 09:25 | 407.80 | 1226 | 15:15 | 408.05 | TIME_EXIT | LOSS | -1,035.53 | -0.21% |
| ORB-15 | Price Action | HINDUNILVR | STRONG | 09:40 | 2134.60 | 234 | 15:15 | 2140.17 | TIME_EXIT | LOSS | -2,032.57 | -0.41% |
| RSI-EXT | Indicator | BHARTIARTL | MEDIUM | 09:20 | 1933.70 | 258 | 15:15 | 1939.30 | TIME_EXIT | LOSS | -2,173.03 | -0.44% |
| INTRADAY-STRUCT | Price Action | HCLTECH | MEDIUM | 10:15 | 1206.70 | 414 | 11:20 | 1213.80 | STOP_HIT | LOSS | -3,669.41 | -0.73% |
| FAILED-BO | Price Action | LT | MEDIUM | 09:35 | 3813.30 | 131 | 15:15 | 3840.74 | TIME_EXIT | LOSS | -4,324.34 | -0.87% |
| PIN-BAR | Price Action | SUNPHARMA | MEDIUM | 09:35 | 1942.40 | 257 | 13:21 | 1958.24 | STOP_HIT | LOSS | -4,801.54 | -0.96% |
| REL-STR | Indicator | ADANIENT | STRONG | 09:45 | 3134.30 | 159 | 14:00 | 3178.93 | STOP_HIT | LOSS | -7,826.92 | -1.57% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 0 WIN, 8 LOSS — net **-₹25,142.92** — avg P&L/trade **-0.56%**

### Day totals — 2026-07-20

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 4 | 2 | 12 | **-₹35,220.37** | **-0.39%** |

**Move-strength breakdown, first day of real data** (6 STRONG / 10 MEDIUM / 2 LOW, 0 UNRATED):
STRONG-tagged trades actually did worst today (avg -0.75%) vs MEDIUM (-0.20%) and LOW (-0.27%) —
the opposite of what the tier is meant to signal. With only 18 trades on day one, this is noise, not
a verdict — the tier isn't driving any decision yet and won't until there's enough of a sample
(weeks, not a day) to test it properly, per the earlier statistical-validation discussion.

---

## 2026-07-21

Fifth live session — heaviest loss day so far. 14 of 18 trades closed LOSS, and both sides were
negative (LONG -₹40,788.91, SHORT -₹9,595.70). No fill voids or incomplete exits in the log.

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PIN-BAR | Price Action | ADANIGREEN | LOW | 09:35 | 1532.10 | 326 | 10:13 | 1549.12 | TARGET_HIT | EXACT_WIN | +4,817.03 | +0.96% |
| FAILED-BD | Price Action | AXISBANK | STRONG | 09:35 | 1256.40 | 397 | 15:15 | 1256.44 | TIME_EXIT | LOSS | -712.27 | -0.14% |
| VPOC | Indicator | ADANIPOWER | LOW | 09:20 | 220.09 | 2271 | 15:15 | 220.06 | TIME_EXIT | LOSS | -811.86 | -0.16% |
| INTRADAY-STRUCT | Price Action | DLF | MEDIUM | 10:15 | 671.75 | 744 | 10:40 | 668.54 | STOP_HIT | LOSS | -3,118.62 | -0.62% |
| REL-STR | Indicator | BSE | MEDIUM | 09:45 | 3690.00 | 135 | 15:15 | 3665.40 | TIME_EXIT | LOSS | -4,044.76 | -0.81% |
| ORB-15 | Price Action | EICHERMOT | MEDIUM | 09:40 | 7629.50 | 65 | 13:00 | 7575.94 | STOP_HIT | LOSS | -4,201.78 | -0.85% |
| SUPERTREND | Indicator | INFY | STRONG | 09:25 | 1092.10 | 457 | 10:23 | 1074.50 | STOP_HIT | LOSS | -8,764.50 | -1.76% |
| RSI-EXT | Indicator | AEGISLOG | LOW | 09:20 | 1371.36 | 364 | 11:55 | 1340.89 | STOP_HIT | LOSS | -11,810.11 | -2.37% |
| VWAP-REV | Indicator | PAYTM | STRONG | 09:55 | 1332.50 | 375 | 13:28 | 1302.04 | STOP_HIT | LOSS | -12,142.04 | -2.43% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 0 WIN, 8 LOSS — net **-₹40,788.91** — avg P&L/trade **-0.91%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| REL-STR | Indicator | BANKBARODA | STRONG | 09:45 | 252.95 | 1976 | 15:15 | 247.50 | TIME_EXIT | WIN | +10,046.68 | +2.01% |
| VPOC | Indicator | CGPOWER | LOW | 09:20 | 913.65 | 547 | 10:34 | 903.62 | TARGET_HIT | EXACT_WIN | +4,762.65 | +0.95% |
| RSI-EXT | Indicator | ADANIENT | MEDIUM | 09:20 | 3199.10 | 156 | 15:15 | 3182.81 | TIME_EXIT | WIN | +1,814.93 | +0.36% |
| PIN-BAR | Price Action | GVT&D | MEDIUM | 09:35 | 4477.84 | 111 | 15:15 | 4485.50 | TIME_EXIT | LOSS | -1,576.36 | -0.32% |
| INTRADAY-STRUCT | Price Action | BEL | LOW | 10:15 | 408.10 | 1225 | 14:53 | 409.80 | STOP_HIT | LOSS | -2,812.49 | -0.56% |
| VWAP-REV | Indicator | KALYANKJIL | STRONG | 11:35 | 573.70 | 871 | 15:15 | 577.00 | TIME_EXIT | LOSS | -3,604.43 | -0.72% |
| ORB-15 | Price Action | HINDALCO | STRONG | 10:05 | 945.35 | 528 | 15:15 | 951.05 | TIME_EXIT | LOSS | -3,739.06 | -0.75% |
| SUPERTREND | Indicator | AXISBANK | STRONG | 09:25 | 1249.40 | 400 | 09:57 | 1265.63 | STOP_HIT | LOSS | -7,224.29 | -1.45% |
| FAILED-BO | Price Action | ADANIENSOL | STRONG | 09:35 | 1728.30 | 289 | 13:55 | 1750.90 | STOP_HIT | LOSS | -7,263.33 | -1.45% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 2 WIN, 6 LOSS — net **-₹9,595.70** — avg P&L/trade **-0.21%**

### Day totals — 2026-07-21

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 2 | 2 | 14 | **-₹50,384.61** | **-0.56%** |

**Move-strength breakdown** (8 STRONG / 5 MEDIUM / 5 LOW, 0 UNRATED): STRONG-tagged trades were the
worst-performing tier again today (avg -0.84%) vs MEDIUM (-0.45%) and LOW (-0.24%) — same direction
as 2026-07-20. Two days of data in the same direction is still not a real signal, but it's now two
for two against the tier's intended meaning rather than one — worth continuing to watch, not acting on.

---

## 2026-07-22

Sixth live session — 17 trades instead of the usual 18 (`FAILED-BD` SHORT, `FAILED-BO` LONG, and
`VWAP-REV` SHORT never got a qualifying signal or fill today — not a bug, just no valid setup fired
for those three strategy/side slots). Another losing day, though less severe than 07-21.

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | Indicator | GVT&D | STRONG | 09:55 | 4446.50 | 112 | 15:15 | 4481.10 | TIME_EXIT | WIN | +3,145.54 | +0.63% |
| VPOC | Indicator | BHARTIARTL | LOW | 09:20 | 1946.00 | 256 | 12:42 | 1948.57 | TARGET_HIT | EXACT_WIN | -70.14 | -0.01% |
| FAILED-BD | Price Action | ADANIENT | LOW | 09:35 | 3161.75 | 157 | 09:49 | 3152.75 | STOP_HIT | LOSS | -2,134.76 | -0.43% |
| RSI-EXT | Indicator | AXISBANK | STRONG | 09:20 | 1243.60 | 402 | 15:15 | 1239.10 | TIME_EXIT | LOSS | -2,536.38 | -0.51% |
| INTRADAY-STRUCT | Price Action | ETERNAL | MEDIUM | 10:15 | 287.60 | 1738 | 12:29 | 285.45 | STOP_HIT | LOSS | -4,462.45 | -0.89% |
| ORB-15 | Price Action | SUZLON | STRONG | 11:00 | 53.29 | 9382 | 13:24 | 52.89 | STOP_HIT | LOSS | -4,499.03 | -0.90% |
| PIN-BAR | Price Action | ADANIPOWER | MEDIUM | 09:35 | 220.46 | 2267 | 09:35 | 218.19 | STOP_HIT | LOSS | -5,865.96 | -1.17% |
| SUPERTREND | Indicator | DIXON | MEDIUM | 09:25 | 14170.00 | 35 | 10:26 | 14021.00 | STOP_HIT | LOSS | -5,934.26 | -1.20% |
| REL-STR | Indicator | AEGISLOG | MEDIUM | 09:45 | 1354.40 | 369 | 10:39 | 1336.57 | STOP_HIT | LOSS | -7,302.86 | -1.46% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 1 WIN, 7 LOSS — net **-₹29,660.30** — avg P&L/trade **-0.66%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-15 | Price Action | TMPV | STRONG | 09:40 | 331.85 | 1506 | 15:15 | 328.10 | TIME_EXIT | WIN | +4,922.14 | +0.98% |
| INTRADAY-STRUCT | Price Action | DIXON | MEDIUM | 10:15 | 14071.00 | 35 | 11:14 | 13984.06 | TARGET_HIT | EXACT_WIN | +2,326.08 | +0.47% |
| PIN-BAR | Price Action | BAJFINANCE | LOW | 09:35 | 1065.00 | 469 | 15:15 | 1060.60 | TIME_EXIT | WIN | +1,336.57 | +0.27% |
| SUPERTREND | Indicator | TATASTEEL | STRONG | 09:25 | 186.54 | 2680 | 15:15 | 186.56 | TIME_EXIT | LOSS | -787.22 | -0.16% |
| FAILED-BO | Price Action | HCLTECH | MEDIUM | 09:35 | 1234.60 | 404 | 15:15 | 1237.85 | TIME_EXIT | LOSS | -2,042.30 | -0.41% |
| VPOC | Indicator | NTPC | LOW | 09:20 | 346.90 | 1441 | 11:33 | 348.40 | STOP_HIT | LOSS | -2,891.49 | -0.58% |
| REL-STR | Indicator | ADANIENSOL | STRONG | 09:45 | 1730.00 | 289 | 11:35 | 1755.96 | STOP_HIT | LOSS | -8,234.86 | -1.65% |
| RSI-EXT | Indicator | BAJAJ-AUTO | MEDIUM | 09:20 | 10661.36 | 46 | 11:22 | 10878.09 | STOP_HIT | LOSS | -10,691.05 | -2.18% |

**SHORT summary**: 8 trades — 1 EXACT_WIN, 2 WIN, 5 LOSS — net **-₹16,062.13** — avg P&L/trade **-0.41%**

### Day totals — 2026-07-22

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 17 | 2 | 3 | 12 | **-₹45,722.43** | **-0.54%** |

**Move-strength breakdown** (6 STRONG / 7 MEDIUM / 4 LOW, 0 UNRATED): this time MEDIUM was worst
(avg -0.98%), STRONG second (-0.27%), LOW best (-0.19%) — a different ordering than the previous two
days, which undercuts even the loose "STRONG underperforms" pattern from 07-20/07-21. Three days in,
the tier still shows no consistent relationship with outcome either way — exactly the noisy, small-n
behavior expected this early, and still not something to act on.

---

## 2026-07-23

Seventh live session — third losing day in a row. 18 trades (`FAILED-BD` SHORT and `FAILED-BO` LONG
never got a qualifying signal today). Both sides negative again, though SHORT held up much better
than LONG (LONG -₹44,163.81 vs SHORT -₹8,328.83).

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| REL-STR | Indicator | BAJAJ-AUTO | MEDIUM | 09:45 | 11041.00 | 45 | 15:15 | 11274.50 | TIME_EXIT | WIN | +9,774.57 | +1.97% |
| VPOC | Indicator | AEGISLOG | LOW | 09:20 | 1357.00 | 368 | 09:21 | 1365.29 | TARGET_HIT | EXACT_WIN | +2,319.42 | +0.46% |
| PIN-BAR | Price Action | AXISBANK | STRONG | 09:35 | 1233.30 | 405 | 12:31 | 1224.15 | STOP_HIT | LOSS | -4,430.58 | -0.89% |
| INTRADAY-STRUCT | Price Action | CANBK | STRONG | 10:15 | 127.18 | 3931 | 12:42 | 125.69 | STOP_HIT | LOSS | -6,571.60 | -1.31% |
| ORB-15 | Price Action | TRENT | STRONG | 09:40 | 2910.26 | 172 | 13:30 | 2875.01 | STOP_HIT | LOSS | -6,787.68 | -1.36% |
| FAILED-BD | Price Action | ADANIENSOL | MEDIUM | 09:35 | 1717.70 | 291 | 09:43 | 1696.15 | STOP_HIT | LOSS | -6,993.74 | -1.40% |
| SUPERTREND | Indicator | INDIGO | STRONG | 09:25 | 5120.50 | 97 | 13:08 | 5041.29 | STOP_HIT | LOSS | -8,401.81 | -1.69% |
| RSI-EXT | Indicator | ADANIGREEN | STRONG | 09:20 | 1413.10 | 353 | 13:22 | 1384.45 | STOP_HIT | LOSS | -10,833.40 | -2.17% |
| VWAP-REV | Indicator | OFSS | STRONG | 09:45 | 10870.00 | 45 | 09:45 | 10613.69 | STOP_HIT | LOSS | -12,238.99 | -2.50% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 1 WIN, 7 LOSS — net **-₹44,163.81** — avg P&L/trade **-0.99%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VWAP-REV | Indicator | ETERNAL | STRONG | 10:10 | 292.50 | 1709 | 13:01 | 287.77 | TARGET_HIT | EXACT_WIN | +7,356.47 | +1.47% |
| VPOC | Indicator | IDEA | MEDIUM | 09:20 | 13.44 | 37202 | 14:28 | 13.28 | TARGET_HIT | EXACT_WIN | +5,226.82 | +1.05% |
| SUPERTREND | Indicator | BHEL | LOW | 09:30 | 413.80 | 1208 | 15:15 | 410.05 | TIME_EXIT | WIN | +3,804.01 | +0.76% |
| ORB-15 | Price Action | TITAN | MEDIUM | 09:45 | 4698.50 | 106 | 12:27 | 4677.33 | TARGET_HIT | EXACT_WIN | +1,519.48 | +0.31% |
| INTRADAY-STRUCT | Price Action | ONGC | LOW | 10:15 | 252.49 | 1980 | 15:15 | 252.33 | TIME_EXIT | LOSS | -409.59 | -0.08% |
| FAILED-BO | Price Action | HINDUNILVR | MEDIUM | 09:35 | 2155.60 | 231 | 15:15 | 2162.87 | TIME_EXIT | LOSS | -2,407.37 | -0.48% |
| PIN-BAR | Price Action | SUNPHARMA | MEDIUM | 09:35 | 1933.00 | 258 | 10:49 | 1946.80 | STOP_HIT | LOSS | -4,289.59 | -0.86% |
| REL-STR | Indicator | ADANIENSOL | STRONG | 09:45 | 1694.80 | 295 | 11:05 | 1720.50 | STOP_HIT | LOSS | -8,314.70 | -1.66% |
| RSI-EXT | Indicator | BAJAJ-AUTO | STRONG | 09:20 | 11106.00 | 45 | 11:40 | 11330.00 | STOP_HIT | LOSS | -10,814.36 | -2.16% |

**SHORT summary**: 9 trades — 3 EXACT_WIN, 1 WIN, 5 LOSS — net **-₹8,328.83** — avg P&L/trade **-0.18%**

### Day totals — 2026-07-23

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 4 | 2 | 12 | **-₹52,492.64** | **-0.59%** |

**Move-strength breakdown** (9 STRONG / 6 MEDIUM / 3 LOW, 0 UNRATED): STRONG was clearly the worst
tier again today (avg -1.36%) vs MEDIUM (+0.10%) and LOW (+0.38%). Pooled across all 4 days the
classifier has been live (2026-07-20 through 07-23, 71 trades), the pattern is now consistent and
monotonic in the *wrong* direction — LOW -0.10% avg / 50% win rate, MEDIUM -0.38% / 28.6% win rate,
STRONG -0.87% / 20.7% win rate. That's four days running of STRONG underperforming, not one-off
noise anymore — but 29 STRONG trades is still short of the ~50-100/tier the earlier statistical-
validation discussion set as a minimum before trusting a per-tier read, so this stays observational
only for now. Worth watching closely; not yet a basis for any sizing/filtering decision.

---

## 2026-07-24

Eighth live session — fourth losing day in a row. Two exits couldn't fully fill near their trigger
price: SUPERTREND CGPOWER sold only 194/561 shares (34.6%) at the stop, and VWAP-REV HFCL's
time-exit found **zero** fillable shares in the book (see caveat below).

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-15 | Price Action | HSCL | STRONG | 09:45 | 781.40 | 639 | 15:15 | 790.98 | TIME_EXIT | WIN | +5,389.23 | +1.08% |
| INTRADAY-STRUCT | Price Action | TRENT | LOW | 10:15 | 2844.62 | 175 | 10:47 | 2867.59 | TARGET_HIT | EXACT_WIN | +3,290.39 | +0.66% |
| REL-STR | Indicator | ADANIENSOL | MEDIUM | 09:45 | 1693.20 | 295 | 15:15 | 1705.20 | TIME_EXIT | WIN | +2,808.98 | +0.56% |
| FAILED-BD | Price Action | ADANIENT | STRONG | 09:35 | 3016.43 | 165 | 15:15 | 3028.58 | TIME_EXIT | WIN | +1,276.72 | +0.26% |
| VPOC | Indicator | BSE | LOW | 09:20 | 3570.40 | 140 | 09:24 | 3552.02 | STOP_HIT | LOSS | -3,299.38 | -0.66% |
| PIN-BAR | Price Action | BANKBARODA | STRONG | 09:35 | 241.85 | 2067 | 10:14 | 240.41 | STOP_HIT | LOSS | -3,705.87 | -0.74% |
| VWAP-REV | Indicator | HFCL | STRONG | 09:45 | 198.49 | 2519 | 15:15 | 196.66 | TIME_EXIT | LOSS | -5,335.03 | -1.07% |
| RSI-EXT | Indicator | BAJFINANCE | MEDIUM | 09:20 | 1025.60 | 487 | 10:15 | 1005.10 | STOP_HIT | LOSS | -10,703.28 | -2.14% |
| SUPERTREND | Indicator | CGPOWER | STRONG | 09:25 | 890.90 | 561 | 14:24 | 868.90 | STOP_HIT | LOSS | -13,063.32 | -2.61% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 3 WIN, 5 LOSS — net **-₹23,341.56** — avg P&L/trade **-0.52%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-15 | Price Action | BAJFINANCE | STRONG | 09:45 | 1020.30 | 490 | 15:15 | 1011.40 | TIME_EXIT | WIN | +3,634.66 | +0.73% |
| VPOC | Indicator | ADANIENT | STRONG | 09:25 | 3016.73 | 165 | 09:27 | 3004.32 | TARGET_HIT | EXACT_WIN | +1,322.31 | +0.27% |
| VWAP-REV | Indicator | ADANIGREEN | STRONG | 11:50 | 1396.50 | 358 | 15:15 | 1395.90 | TIME_EXIT | LOSS | -513.91 | -0.10% |
| RSI-EXT | Indicator | HCLTECH | STRONG | 09:20 | 1270.30 | 393 | 15:15 | 1272.30 | TIME_EXIT | LOSS | -1,514.31 | -0.30% |
| SUPERTREND | Indicator | BEL | STRONG | 09:25 | 403.45 | 1239 | 15:15 | 405.35 | TIME_EXIT | LOSS | -3,084.18 | -0.62% |
| PIN-BAR | Price Action | ITC | STRONG | 09:35 | 280.80 | 1780 | 10:24 | 282.15 | STOP_HIT | LOSS | -3,133.04 | -0.63% |
| REL-STR | Indicator | BHARTIARTL | STRONG | 09:45 | 1888.20 | 264 | 15:15 | 1898.10 | TIME_EXIT | LOSS | -3,341.94 | -0.67% |
| INTRADAY-STRUCT | Price Action | BHEL | MEDIUM | 10:15 | 403.75 | 1238 | 11:10 | 406.35 | STOP_HIT | LOSS | -3,948.94 | -0.79% |
| FAILED-BO | Price Action | POLICYBZR | STRONG | 11:30 | 1513.50 | 330 | 12:54 | 1528.79 | STOP_HIT | LOSS | -5,776.15 | -1.16% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 1 WIN, 7 LOSS — net **-₹16,355.50** — avg P&L/trade **-0.36%**

### Day totals — 2026-07-24

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 2 | 4 | 12 | **-₹39,697.06** | **-0.44%** |

**Missing strategy/side**: `FAILED-BD` SHORT and `FAILED-BO` LONG never fired (third day running for
this same pair — see note after 2026-07-28 below).

**Caveat — VWAP-REV HFCL exit, zero fillable liquidity**: the exit-fill check found **0/2519** shares
fillable anywhere in the book at 15:15 square-off (log: `SOLD only 0/2519 ... INCOMPLETE EXIT`), yet
the CSV records `exit_qty_filled=2519` / `exit_fill_pct=100%` and P&L as if the full quantity closed
at the raw exit price. This is the code's designed fallback for a true zero-liquidity read (distinct
from "depth data unavailable") — `live/top10_agent.py::_exit_fill_check`'s last branch reports the
full share count instead of the real 0 whenever `best_qty` is exactly 0, so `exit_fill_pct` silently
shows 100% for a trade the log itself flags as an unresolved ERROR. Not fixed yet — flagging here so
the number isn't taken at face value.

---

## 2026-07-27

Ninth live session — first roughly-flat day since 07-17, driven almost entirely by SHORT
(+₹8,954.78 vs LONG -₹15,587.62). Two more partial exits: PIN-BAR HEROMOTOCO (86/91, 94.5%) and
RSI-EXT AEGISLOG (122/381, 32.0%) — both correctly reflected in `exit_qty_filled` this time.

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FAILED-BD | Price Action | POWERINDIA | MEDIUM | 09:35 | 31110.00 | 16 | 15:15 | 31509.06 | TIME_EXIT | WIN | +5,654.09 | +1.14% |
| REL-STR | Indicator | BAJFINANCE | STRONG | 09:45 | 1039.70 | 480 | 15:15 | 1047.08 | TIME_EXIT | WIN | +2,814.27 | +0.56% |
| PIN-BAR | Price Action | HEROMOTOCO | MEDIUM | 09:35 | 5064.37 | 91 | 11:09 | 5093.73 | TARGET_HIT | EXACT_WIN | +1,994.71 | +0.43% |
| VPOC | Indicator | BANKBARODA | STRONG | 09:20 | 246.78 | 2026 | 09:20 | 246.74 | STOP_HIT | LOSS | -806.97 | -0.16% |
| VWAP-REV | Indicator | KALYANKJIL | MEDIUM | 11:30 | 566.20 | 883 | 15:15 | 564.53 | TIME_EXIT | LOSS | -2,203.88 | -0.44% |
| SUPERTREND | Indicator | AXISBANK | MEDIUM | 09:25 | 1233.00 | 405 | 15:15 | 1227.00 | TIME_EXIT | LOSS | -3,156.12 | -0.63% |
| INTRADAY-STRUCT | Price Action | GROWW | MEDIUM | 10:15 | 203.23 | 2461 | 10:48 | 202.07 | STOP_HIT | LOSS | -3,575.68 | -0.71% |
| ORB-15 | Price Action | TECHM | LOW | 09:40 | 1588.90 | 314 | 13:18 | 1573.17 | STOP_HIT | LOSS | -5,663.62 | -1.14% |
| RSI-EXT | Indicator | AEGISLOG | LOW | 09:20 | 1310.90 | 381 | 14:50 | 1284.85 | STOP_HIT | LOSS | -10,644.42 | -2.13% |

**LONG summary**: 9 trades — 1 EXACT_WIN, 2 WIN, 6 LOSS — net **-₹15,587.62** — avg P&L/trade **-0.34%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-15 | Price Action | ONGC | STRONG | 09:40 | 243.10 | 2056 | 15:15 | 238.57 | TIME_EXIT | WIN | +8,584.75 | +1.72% |
| VWAP-REV | Indicator | OFSS | STRONG | 09:45 | 11155.00 | 44 | 10:04 | 10988.95 | TARGET_HIT | EXACT_WIN | +6,593.78 | +1.34% |
| RSI-EXT | Indicator | ADANIGREEN | STRONG | 09:20 | 1410.60 | 354 | 15:15 | 1401.54 | TIME_EXIT | WIN | +2,480.11 | +0.50% |
| FAILED-BO | Price Action | ADANIPOWER | LOW | 09:35 | 215.05 | 2325 | 15:15 | 213.88 | TIME_EXIT | WIN | +1,992.91 | +0.40% |
| REL-STR | Indicator | ADANIENSOL | LOW | 09:45 | 1708.90 | 292 | 15:15 | 1701.72 | TIME_EXIT | WIN | +1,370.85 | +0.27% |
| SUPERTREND | Indicator | BANKBARODA | STRONG | 09:25 | 244.40 | 2045 | 15:15 | 244.00 | TIME_EXIT | WIN | +89.83 | +0.02% |
| INTRADAY-STRUCT | Price Action | HEROMOTOCO | LOW | 10:15 | 5059.50 | 98 | 10:52 | 5090.00 | STOP_HIT | LOSS | -3,713.93 | -0.75% |
| VPOC | Indicator | TECHM | LOW | 09:20 | 1577.10 | 317 | 09:26 | 1587.15 | STOP_HIT | LOSS | -3,915.35 | -0.78% |
| PIN-BAR | Price Action | BAJFINANCE | MEDIUM | 09:35 | 1030.00 | 485 | 09:37 | 1037.83 | STOP_HIT | LOSS | -4,528.17 | -0.91% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 5 WIN, 3 LOSS — net **+₹8,954.78** — avg P&L/trade **+0.20%**

### Day totals — 2026-07-27

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 2 | 7 | 9 | **-₹6,632.84** | **-0.07%** |

**Missing strategy/side**: `FAILED-BD` SHORT and `FAILED-BO` LONG again (see note below).

---

## 2026-07-28

Tenth live session — back to a clear loss. Two more partial exits: ORB-15 M&M (70/154, 45.5%, still
an EXACT_WIN on P&L despite the shortfall) and VWAP-REV HSCL (501/654, 76.6%).

### LONG

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| REL-STR | Indicator | COFORGE | STRONG | 09:45 | 1662.20 | 299 | 15:15 | 1688.55 | TIME_EXIT | WIN | +7,147.05 | +1.44% |
| ORB-15 | Price Action | M&M | STRONG | 09:40 | 3242.30 | 154 | 13:01 | 3279.67 | TARGET_HIT | EXACT_WIN | +5,022.01 | +1.01% |
| INTRADAY-STRUCT | Price Action | HINDALCO | STRONG | 10:15 | 940.15 | 531 | 10:40 | 944.99 | TARGET_HIT | EXACT_WIN | +1,839.72 | +0.37% |
| PIN-BAR | Price Action | BAJFINANCE | LOW | 09:35 | 1047.40 | 477 | 15:15 | 1047.20 | TIME_EXIT | LOSS | -823.70 | -0.16% |
| FAILED-BD | Price Action | ADANIENT | MEDIUM | 09:35 | 3014.77 | 165 | 15:15 | 3002.38 | TIME_EXIT | LOSS | -2,768.60 | -0.56% |
| VPOC | Indicator | HDFCBANK | STRONG | 09:20 | 738.45 | 677 | 09:51 | 734.62 | STOP_HIT | LOSS | -3,321.86 | -0.66% |
| SUPERTREND | Indicator | ITC | STRONG | 09:25 | 286.75 | 1743 | 11:22 | 284.20 | STOP_HIT | LOSS | -5,169.78 | -1.03% |
| RSI-EXT | Indicator | BEL | STRONG | 09:20 | 396.95 | 1259 | 14:17 | 389.00 | STOP_HIT | LOSS | -10,729.71 | -2.15% |
| VWAP-REV | Indicator | HSCL | STRONG | 09:45 | 764.25 | 654 | 09:45 | 747.62 | STOP_HIT | LOSS | -11,597.14 | -2.32% |

**LONG summary**: 9 trades — 2 EXACT_WIN, 1 WIN, 6 LOSS — net **-₹20,402.01** — avg P&L/trade **-0.45%**

### SHORT

| Strategy | Type | Symbol | Strength | Entry Time | Entry Price | Qty | Exit Time | Exit Price | Exit Reason | Result | P&L (₹) | P&L % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SUPERTREND | Indicator | MCX | LOW | 09:30 | 2752.82 | 182 | 15:15 | 2709.00 | TIME_EXIT | WIN | +7,249.37 | +1.45% |
| VPOC | Indicator | KOTAKBANK | MEDIUM | 09:20 | 385.70 | 1296 | 09:46 | 384.30 | TARGET_HIT | EXACT_WIN | +1,086.71 | +0.22% |
| REL-STR | Indicator | ADANIENT | LOW | 09:45 | 3012.80 | 165 | 15:15 | 3003.32 | TIME_EXIT | WIN | +840.12 | +0.17% |
| PIN-BAR | Price Action | BHARTIARTL | STRONG | 09:35 | 1899.90 | 263 | 15:15 | 1900.86 | TIME_EXIT | LOSS | -980.11 | -0.20% |
| INTRADAY-STRUCT | Price Action | BAJFINANCE | LOW | 10:15 | 1045.40 | 478 | 15:15 | 1047.30 | TIME_EXIT | LOSS | -1,637.22 | -0.33% |
| VWAP-REV | Indicator | SWIGGY | STRONG | 10:45 | 267.20 | 1871 | 15:15 | 267.97 | TIME_EXIT | LOSS | -2,165.18 | -0.43% |
| ORB-15 | Price Action | SBIN | STRONG | 10:10 | 1014.60 | 492 | 10:43 | 1020.00 | STOP_HIT | LOSS | -3,386.12 | -0.68% |
| FAILED-BO | Price Action | POLYCAB | MEDIUM | 09:35 | 9013.00 | 55 | 10:39 | 9111.95 | STOP_HIT | LOSS | -6,168.68 | -1.24% |
| RSI-EXT | Indicator | COFORGE | STRONG | 09:20 | 1625.20 | 307 | 09:32 | 1657.72 | STOP_HIT | LOSS | -10,715.87 | -2.15% |

**SHORT summary**: 9 trades — 1 EXACT_WIN, 2 WIN, 6 LOSS — net **-₹15,876.98** — avg P&L/trade **-0.35%**

### Day totals — 2026-07-28

| Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|
| 18 | 3 | 3 | 12 | **-₹36,278.99** | **-0.40%** |

**Missing strategy/side, 5 of the last 6 sessions**: `FAILED-BD` SHORT and `FAILED-BO` LONG have not
fired since 2026-07-21 (absent on 07-22, 07-23, 07-24, 07-27, 07-28). That's too consistent to be
random day-to-day variation — worth checking whether these two strategy/side combinations still have
a live signal path at all, separate from just "market didn't offer a setup."

**Move-strength, pooled since 2026-07-20 (7 sessions, 125 trades)**: avg P&L% still orders the same
way as every prior update — LOW best (-0.17%, 46.2% win rate) → MEDIUM (-0.39%, 30.0%) → STRONG
worst (-0.57%, 30.5%) — now on a much larger STRONG sample (n=59). Still purely observational, still
not acted on, but the ordering has held for 7 straight sessions now.

---

## Running totals (all days)

| Date | Trades | EXACT_WIN | WIN | LOSS | Net P&L | Avg P&L %/trade |
|---|---|---|---|---|---|---|
| 2026-07-15 | 18 | 3 | 7 | 8 | +₹46,556.81 | +0.52% |
| 2026-07-16 | 18 | 4 | 5 | 9 | +₹5,445.54 | +0.06% |
| 2026-07-17 | 18 | 4 | 4 | 10 | -₹6,625.54 | -0.07% |
| 2026-07-20 | 18 | 4 | 2 | 12 | -₹35,220.37 | -0.39% |
| 2026-07-21 | 18 | 2 | 2 | 14 | -₹50,384.61 | -0.56% |
| 2026-07-22 | 17 | 2 | 3 | 12 | -₹45,722.43 | -0.54% |
| 2026-07-23 | 18 | 4 | 2 | 12 | -₹52,492.64 | -0.59% |
| 2026-07-24 | 18 | 2 | 4 | 12 | -₹39,697.06 | -0.44% |
| 2026-07-27 | 18 | 2 | 7 | 9 | -₹6,632.84 | -0.07% |
| 2026-07-28 | 18 | 3 | 3 | 12 | -₹36,278.99 | -0.40% |
| **Total** | **179** | **30** | **39** | **110** | **-₹221,052.13** | **-0.25%** |

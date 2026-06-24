# Trading Agent — Full Architecture & Build Plan
**Last updated: 2026-05-30**
**Status: Planning complete — ready to build**

---

## 1. WHAT WE ARE BUILDING

An intraday cash equity **recommendation system** (not auto-execution) for NSE Nifty 500 stocks.

| Parameter | Value |
|---|---|
| Data interval | 5-minute OHLCV candles |
| Data source | Kite Connect API (somal_trading, active) — has data from Jan 2015 |
| Download strategy | 1 year at a time, year by year (2016 → 2017 → ... → 2026) |
| Learning phase | 2016 – 2022 (7 years, weights calibrate year by year) |
| Testing phase | 2023 – 2026 YTD (weights FROZEN after 2022, unseen holdout) |
| Universe | Nifty 500 stocks (current list) |
| Capital | Rs 10,00,000 |
| Max positions | 3 concurrent |
| Goal | Minimum 3% return per month |
| Execution | Manual — system recommends, human executes |

---

## 2. HOW THE SYSTEM WORKS (Big Picture)

```
SESSION 1: Download 2016 → Process all 2016 trading days → Save checkpoint
SESSION 2: Download 2017 → Process all 2017 trading days → Save checkpoint
...
SESSION 7: Download 2022 → Process all 2022 days → FREEZE weights → Save checkpoint
SESSION 8: Download 2023 → TEST mode (frozen weights) → Record P&L → Save checkpoint
...
SESSION 11: Download 2026 YTD → TEST → Final VectorBT performance report

EACH SESSION (manual trigger via Claude VSCode):
─────────────────────────────────────────────────
User prompts: "Continue trading agent analysis"
  → Claude reads checkpoints/progress.json
  → Sees last_completed_year = 2017, next = 2018
  → Downloads 2018 data for all 500 stocks (~8-10 min)
  → Processes all ~250 trading days of 2018 sequentially
  → 22 strategies run on each day, weights adapt every 20 days
  → Notebooks generated, memory updated
  → Year-end summary written
  → Checkpoint saved → session ends
```

---

## 3. FOLDER STRUCTURE

```
TradingAgent/
│
├── .env                          # API keys (Kite Connect)
├── requirements.txt              # All Python dependencies
├── PLAN.md                       # This document
│
├── config/
│   ├── settings.py               # All constants (capital, limits, costs)
│   ├── universe.csv              # 500 stock symbols + instrument tokens
│   └── trading_calendar.csv     # NSE trading days (no weekends/holidays)
│
├── data/
│   ├── stocks/                   # One Parquet file per stock
│   │   ├── RELIANCE.parquet      # All 5-min candles, 1 year rolling
│   │   ├── HDFCBANK.parquet
│   │   └── ...                   # 500 files total (~450 MB total)
│   ├── index/
│   │   ├── NIFTY50.parquet       # Nifty 50 index 5-min data
│   │   └── INDIAVIX.parquet      # India VIX daily
│   └── daily_liquidity.parquet   # Rolling 20-day avg turnover per stock
│
├── checkpoints/
│   ├── download_progress.json    # Which stocks downloaded, up to what date
│   ├── analysis_progress.json    # Which dates processed, last notebook generated
│   └── strategy_weights.json     # Current weights for all 22 strategies
│
├── memory/
│   ├── strategy_agent.md         # Weight table, stock patterns, regime guide
│   ├── lessons.md                # Numbered lessons, most recent first
│   └── session_log.md            # One entry per Claude session (what was done)
│
├── strategies/
│   ├── __init__.py
│   ├── base.py                   # BaseStrategy class all strategies inherit
│   ├── breakout/
│   │   ├── orb.py                # Strategy 1 & 2: ORB-15, ORB-30
│   │   ├── pdh_pdl.py            # Strategy 3: Previous Day High/Low
│   │   ├── gap_continuation.py   # Strategy 4: Gap continuation
│   │   └── volume_spike.py       # Strategy 5: Volume spike breakout
│   ├── mean_reversion/
│   │   ├── vwap_reversion.py     # Strategy 6: VWAP reversion
│   │   ├── rsi_extremes.py       # Strategy 7: RSI < 25 / > 75
│   │   ├── bollinger.py          # Strategy 8: BB reversion
│   │   └── gap_fade.py           # Strategy 9: Gap fade
│   ├── trend/
│   │   ├── ema_crossover.py      # Strategy 10: 9/21 EMA cross
│   │   ├── supertrend.py         # Strategy 11: Supertrend (10,3)
│   │   └── macd.py               # Strategy 12: MACD crossover
│   ├── price_action/
│   │   ├── sr_breakout.py        # Strategy 13: Support/Resistance breakout
│   │   ├── nr7_inside.py         # Strategy 14: NR7 / Inside Day
│   │   └── first_candle.py       # Strategy 15: First 5-min candle
│   ├── pivot/
│   │   ├── cpr.py                # Strategy 16: Central Pivot Range
│   │   └── camarilla.py          # Strategy 17: Camarilla Pivots
│   ├── volatility/
│   │   ├── adx_filter.py         # Strategy 18: ADX filter (overlay)
│   │   └── vwap_stddev.py        # Strategy 19: VWAP SD Bands
│   ├── oscillator/
│   │   ├── stochastic.py         # Strategy 20: Stochastic crossover
│   │   └── volume_profile.py     # Strategy 21: VPOC / Volume Profile
│   └── market_relative/
│       └── relative_strength.py  # Strategy 22: Stock vs Nifty 50
│
├── backtester/
│   ├── __init__.py
│   ├── engine.py                 # Core sequential day-by-day simulator
│   ├── position_sizer.py         # Position sizing formula
│   ├── cost_model.py             # Brokerage, STT, slippage calculator
│   ├── quality_filter.py         # 6-condition minimum quality check
│   └── composite_scorer.py       # Weighted composite score per stock
│
├── weights/
│   ├── __init__.py
│   ├── adaptive.py               # Weight update logic (every 20 days)
│   └── regime.py                 # VIX/ADX regime override multipliers
│
├── data_pipeline/
│   ├── __init__.py
│   ├── downloader.py             # Kite Connect chunked downloader
│   ├── updater.py                # Daily incremental update (yesterday's data)
│   ├── liquidity.py              # 20-day rolling turnover calculator
│   └── universe.py               # Load and validate stock universe
│
├── notebooks/
│   └── daily/
│       ├── 2025-05-01.ipynb      # One notebook per trading day processed
│       ├── 2025-05-02.ipynb
│       └── ...
│
├── reports/
│   └── vectorbt/                 # VectorBT performance reports (Phase 2)
│
└── scripts/
    ├── bootstrap.py              # ONE-TIME: download 1 year + process all days
    ├── daily_run.py              # DAILY: download yesterday + today's recommendations
    └── generate_report.py        # Run VectorBT analysis on processed data
```

---

## 4. DATA PIPELINE

### 4a. Bootstrap Download (one-time, ~20-30 minutes)

```
Kite Connect API
      │
      ▼
downloader.py
  ├── Load universe.csv (500 symbols + instrument tokens)
  ├── For each stock:
  │     ├── Check download_progress.json → skip if already downloaded
  │     ├── Chunk date range into 100-day windows (5-min limit per request)
  │     │   (1 year = 250 trading days → 3 API calls per stock)
  │     ├── Call kite.historical_data(token, from, to, "5minute")
  │     ├── Sleep 0.35s between calls (stay under 3 req/sec limit)
  │     ├── Retry with exponential backoff on failure (max 3 retries)
  │     ├── Save to data/stocks/SYMBOL.parquet (append mode)
  │     └── Mark stock complete in download_progress.json
  ├── Also download: NIFTY50 index + INDIAVIX
  └── Log final summary to memory/session_log.md
```

**download_progress.json structure:**
```json
{
  "last_updated": "2025-05-30T08:45:00",
  "target_from": "2024-05-30",
  "target_to": "2025-05-30",
  "completed": ["RELIANCE", "HDFCBANK", "TCS", "..."],
  "pending": ["ADANIENT", "..."],
  "failed": [],
  "total_api_calls": 1500,
  "download_time_seconds": 520
}
```

### 4b. Daily Update (each morning, ~3-5 minutes)

```
updater.py
  ├── Read analysis_progress.json → get last_processed_date
  ├── Download all stocks from (last_processed_date + 1) to yesterday
  │   (1 API call per stock = 500 calls, ~3 minutes)
  ├── Append new rows to each stock's Parquet file
  ├── Recalculate daily_liquidity.parquet
  └── Update download_progress.json
```

---

## 5. SEQUENTIAL BACKTESTER (engine.py)

This is the core of Phase 1. It simulates running live, day by day, with no look-ahead.

```python
# Pseudocode — actual implementation in backtester/engine.py

for each trading_day in date_range:

    # 1. Load data — only what was available BEFORE this day
    day_data = load_data_up_to(trading_day - 1 day)
    todays_5min = load_todays_candles(trading_day)   # as they unfold

    # 2. Market context
    nifty_direction = get_nifty_trend(trading_day)
    vix = get_vix(trading_day)
    regime = classify_regime(vix, adx)               # HIGH_VIX / TRENDING / SIDEWAYS

    # 3. Liquidity filter — exclude illiquid stocks
    tradeable_stocks = filter_by_liquidity(stocks, trading_day)

    # 4. Run all 22 strategies on each tradeable stock
    signals = {}
    for stock in tradeable_stocks:
        for strategy in all_22_strategies:
            signal = strategy.generate_signal(stock_data, trading_day)
            # signal = {direction: +1/0/-1, entry, target, stop, reason}
            # Bearish signals (-1): LOGGED but not acted on (long-only system)
            signals[(stock, strategy.name)] = signal

    # 5. Apply regime weight overrides (VIX/ADX modifiers)
    adjusted_weights = regime.apply_overrides(current_weights, vix)

    # 6. Compute composite score per stock
    scores = {}
    for stock in tradeable_stocks:
        score = sum(
            signals[(stock, s.name)].direction * adjusted_weights[s.name]
            for s in all_22_strategies
        )
        scores[stock] = score

    # 7. Apply quality filters to top candidates
    candidates = top_n_by_score(scores, n=10)
    recommendations = []
    for stock in candidates:
        if passes_quality_filter(stock, trading_day, signals):
            size = position_sizer.calculate(stop_loss_pct)
            recommendations.append({stock, entry, target, stop, size, strategies_agreeing})
        if len(recommendations) == 3:
            break

    # 8. Record outcomes (since it's historical, we know what happened)
    for rec in recommendations:
        outcome = simulate_trade(rec, todays_5min)   # hit target / hit stop / time exit
        record_outcome(rec, outcome)

    # 9. Update strategy rolling performance (last 10 signals each)
    for strategy in all_22_strategies:
        strategy.update_performance(outcome)

    # 10. Every 20 trading days: recalculate adaptive weights
    if days_processed % 20 == 0:
        new_weights = adaptive.recalculate(all_22_strategies)
        save_weights(new_weights, checkpoints/strategy_weights.json)
        log_weight_change(new_weights, memory/strategy_agent.md)

    # 11. Generate daily notebook
    notebook_generator.create(trading_day, market_context, signals,
                               recommendations, outcomes, scores)

    # 12. Save checkpoint — so next session resumes from here
    save_checkpoint(trading_day, analysis_progress.json)
```

---

## 6. CHECKPOINT / RESUME SYSTEM

**analysis_progress.json** — what Claude reads when you give the "continue" prompt:

```json
{
  "last_processed_date": "2025-03-15",
  "total_days_processed": 198,
  "total_days_in_range": 250,
  "last_notebook_generated": "2025-03-15",
  "current_strategy_weights": {
    "ORB-15": 1.4,
    "ORB-30": 1.2,
    "VWAP_reversion": 0.5,
    "RSI_extremes": 1.0,
    "...": "..."
  },
  "strategy_performance_window": {
    "ORB-15": {"recent_10_signals": [1,1,0,1,0,1,1,1,0,1], "win_rate": 0.70},
    "...": "..."
  },
  "days_since_weight_update": 12,
  "session_history": [
    {"date": "2026-05-30", "days_processed": 50, "range": "2024-06-01 to 2024-08-15"},
    {"date": "2026-05-31", "days_processed": 75, "range": "2024-08-16 to 2024-11-15"}
  ]
}
```

**When you prompt Claude VSCode:**
Claude reads `analysis_progress.json` → sees `last_processed_date = 2025-03-15` → continues from `2025-03-16` → runs until you stop or all days are done → saves new checkpoint.

---

## 7. COMPOSITE SCORING & QUALITY FILTERS

### Composite Score
```
score(stock) = Σ [ signal(strategy_i) × weight(strategy_i) × regime_modifier(strategy_i) ]

where:
  signal      = +1 (buy), 0 (no signal), -1 (logged but ignored in long-only mode)
  weight      = 0.1 to 3.0 (adaptive, updated every 20 days)
  modifier    = VIX/ADX regime multiplier (0.3 to 1.0)
```

### 6 Quality Filters (ALL must pass to recommend)
1. Liquidity: 20-day avg turnover > Rs 20 Crore
2. Risk:Reward >= 1.5
3. At least 2 independent strategies agree on direction
4. Volume: current > 1.5x same-time-yesterday volume
5. Not in upper/lower circuit
6. Time: no new entries after 2:00 PM IST

### Position Sizing
```
position_size = min(Rs 3,33,333,  Rs 20,000 / stop_loss_pct)
```

### Transaction Cost (included in every trade simulation)
```
total_cost = Rs 40 brokerage + 0.025% STT (sell) + 0.00345% exchange
             + 0.0001% SEBI + 18% GST on brokerage+exchange + 0.003% stamp
Assumed slippage: 0.05% per side
Effective round-trip cost on Rs 3.33L trade: ~Rs 496 (~0.15%)
Break-even: stock must move >0.15% in your favour
```

---

## 8. ADAPTIVE WEIGHT SYSTEM

### Update Rule (every 20 trading days, based on last 10 signals)
```
win_rate > 60%  →  weight × 1.5   (max cap: 3.0)
win_rate 40-60% →  weight × 1.0   (unchanged)
win_rate 30-40% →  weight × 0.5
win_rate < 30%  →  weight × 0.1   (floor: 0.1, never removed)

Revival rule: if weight = 0.1 AND natural regime returns → reset to 0.5
```

### Daily Regime Override (applied before scoring each day)
```
High VIX (>20):         breakout strategy weights × 0.3
Low VIX + ADX > 25:     reversion strategy weights × 0.5
Normal:                 no override
```

### Starting Weights (all initialised at 1.0)
```
All 22 strategies begin at weight = 1.0
The system earns its weights over the first 250 days of data.
```

---

## 9. MEMORY SYSTEM

### memory/strategy_agent.md
Updated every 20 trading days and every year-end:
- Full weight table with trend (rising / falling / stable)
- Stock behaviour patterns (e.g., "HDFCBANK — VWAP reversion very reliable")
- Yearly summaries (which regime dominated, what worked)
- Market regime guide (which strategies win in which conditions)

### memory/lessons.md
One numbered lesson added per session — most recent first:
```
[198] 2026-05-31 — VWAP reversion fails consistently when VIX > 18. 
      Auto-suppress confirmed by weight dropping to 0.1 after 3 losing weeks.
[197] 2026-05-30 — ORB-15 on Mondays has 68% win rate vs 51% overall.
      Day-of-week matters — track separately.
```

### memory/session_log.md
One entry per Claude session:
```
## Session: 2026-05-31
- Downloaded: 500 stocks, 2024-05-30 to 2025-05-29 (bootstrap complete)
- Processed: 2024-05-30 to 2024-08-15 (50 trading days)
- Weights updated: day 20 and day 40
- Notebooks generated: 50
- Next session starts from: 2024-08-16
```

---

## 10. DAILY NOTEBOOK (one per trading day)

**File:** `notebooks/daily/YYYY-MM-DD.ipynb`

### Section A — Market Context
- Nifty 50 direction (gap from prev close, intraday trend)
- India VIX level + regime classification
- Global cues (from Yahoo Finance free data: SGX Nifty, Dow futures)

### Section B — Master DataFrame
One row per stock, columns:
- All 22 strategy signals (+1/0/-1)
- Entry / Target / Stop per strategy
- Composite score
- Rank

### Section C — Top 3 Recommendations
For each: Entry zone, Target (+X%), Stop (-Y%), Position size (Rs + shares), Strategies that agreed, 1-paragraph reasoning

### Section D — Post-Market Review (filled by backtester)
- Outcome of each recommendation (target hit / stop hit / time exit)
- P&L after costs
- What worked and why

### Section E — Running Strategy Leaderboard
Cumulative win rate per strategy across all days processed so far (plotly bar chart)

---

## 11. TRANSACTION COST MODEL (backtester/cost_model.py)

Every simulated trade deducts actual costs before recording P&L:

```python
def calculate_costs(buy_value, sell_value):
    brokerage     = 40                              # Rs 20 × 2 legs
    stt           = sell_value * 0.00025            # 0.025% sell side
    exchange      = (buy_value + sell_value) * 0.0000345
    sebi          = (buy_value + sell_value) * 0.000001
    gst           = (brokerage + exchange) * 0.18
    stamp         = buy_value * 0.00003
    slippage      = (buy_value + sell_value) * 0.0005  # 0.05% each side
    return brokerage + stt + exchange + sebi + gst + stamp + slippage
```

---

## 12. TECHNOLOGY STACK

```
pip install kiteconnect          # Kite Connect API
pip install yfinance             # Yahoo Finance (India VIX, global indices only)
pip install pandas polars pyarrow# Data processing
pip install pandas-ta            # Technical indicators (all 22 strategies)
pip install vectorbt             # Phase 2 performance reports
pip install jupyterlab plotly    # Notebooks and charts
pip install python-dotenv        # .env loading
pip install requests             # HTTP for retries
```

---

## 13. BUILD ORDER (what to build first → what to build last)

### Sprint 1 — Foundation (build this first)
1. `config/settings.py` — all constants, capital, costs, limits
2. `config/universe.csv` — 500 stock symbols + Kite instrument tokens
3. `config/trading_calendar.csv` — NSE trading days
4. `.env` setup and `python-dotenv` loading
5. Project `requirements.txt`

### Sprint 2 — Data Pipeline
6. `data_pipeline/downloader.py` — chunked download with resume
7. `data_pipeline/updater.py` — daily incremental append
8. `data_pipeline/liquidity.py` — 20-day rolling turnover
9. `data_pipeline/universe.py` — load and validate stock list
10. `scripts/bootstrap.py` — one-time full download script

### Sprint 3 — Strategy Library
11. `strategies/base.py` — BaseStrategy class
12. All 22 strategies implemented and unit-tested individually
13. `backtester/composite_scorer.py` — weighted signal aggregation
14. `backtester/quality_filter.py` — 6-condition filter
15. `backtester/cost_model.py` — transaction cost calculator
16. `backtester/position_sizer.py` — position size formula

### Sprint 4 — Backtester Core
17. `backtester/engine.py` — sequential day-by-day simulator
18. `weights/adaptive.py` — 20-day weight recalculation
19. `weights/regime.py` — VIX/ADX regime overrides
20. Checkpoint save/load system

### Sprint 5 — Output & Memory
21. Notebook generator (Section A through E)
22. `memory/` file writers (strategy_agent.md, lessons.md, session_log.md)
23. `scripts/daily_run.py` — full daily pipeline script

### Sprint 6 — Validation & Reports
24. Validate backtester output against known dates
25. `scripts/generate_report.py` — VectorBT performance analysis
26. Per-strategy: Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor

---

## 14. KEY DESIGN DECISIONS & RATIONALE

| Decision | Choice | Reason |
|---|---|---|
| Data interval | 5-min candles | All 22 strategies reference 5-min; manageable size |
| History window | 1 year rolling | Fits in RAM (600 MB), fast download (20 min), daily updates trivial |
| Backtester | Custom Pandas sequential | No look-ahead bias, easy to debug, adaptive weights need day-by-day state |
| Backtesting methodology | Anchored Walk-Forward (5 windows) | Single fixed split gives 1 out-of-sample reading; WF gives 5 independent readings across different regimes (bull, crash, recovery, bear) — essential before deploying real capital |
| Final reports | VectorBT | Vectorized, handles Sharpe/Sortino/Drawdown calculations natively |
| Bearish signals | Phase 2B enables them | Infrastructure already built: Signal(-1) + _sell() + net_pnl(direction=-1) all exist |
| Storage | Parquet (Snappy) | Columnar reads fast for indicator calculation; ~5× smaller than CSV |
| Resume | JSON checkpoints | Claude reads checkpoint on each session start, continues exactly where stopped |
| Memory | Markdown files | Human-readable, Claude can read/write naturally, persists across sessions |
| Universe | Current Nifty 500 | Accepts survivorship bias for now; fix with historical composition list later |
| Trigger | Manual VSCode prompt | User controls when processing happens; checkpoint ensures no work is lost |

---

## 15. KNOWN LIMITATIONS (accepted for now, fix later)

1. **Survivorship bias** — using current Nifty 500 list, not historical composition. Backtests will be ~10-20% optimistic. Fix: obtain NSE historical composition archives.
2. **No shorting (until Phase 2B)** — bearish signals logged but not traded in Phases 1–2. Phase 2B enables short selling with 8 new strategies + independent long/short weights. See trading_agent_req.txt Phase 2B section.
3. **5-min only** — strategies that are most precise on 1-min (e.g., exact ORB breakout tick) will use 5-min approximation. This is acceptable for the current phase.
4. **AWS S3 backup** — not in Phase 1. Add once the system is stable and running daily.
5. **Multi-agent system** — Phase 3. Strategy Agent, News Agent, Recommender Agent etc. are future work after this sequential backtester proves the strategy library.

---

## 16. HOW TO CONTINUE A SESSION (prompt template)

When you open VSCode and want to continue analysis, type:

> "Continue trading agent analysis from checkpoint"

Claude will:
1. Read `checkpoints/analysis_progress.json`
2. Read `checkpoints/strategy_weights.json`
3. Tell you exactly where it left off
4. Ask how many days you want to process this session
5. Continue from the next unprocessed date

---

## 17. PERFORMANCE TARGETS (Phase 2 evaluation)

| Metric | Minimum bar |
|---|---|
| Monthly return | >= 3% |
| Sharpe Ratio | >= 1.5 |
| Max Drawdown | <= 15% (Rs 1,50,000) |
| Profit Factor | >= 1.5 |
| Win Rate | >= 45% |
| Avg Win / Avg Loss | >= 2.0 if win rate < 45% |

---

---

## 18. PHASE 2B — SHORT SIDE BACKTESTING (new phase, before Phase 3)
**Planning date: 2026-06-19**

### What Phase 2B Is

Extends the long-only system to enable short selling (direction=-1 signals that were
already being generated but ignored). Uses the same data, same engine, same cost model.
No separate app — one unified system with a `direction` column in paper_trades.csv.

See `trading_agent_req.txt` Phase 2B section for full strategy rationale, architecture
decisions, and conflict resolution rules.

### New Strategies (10 new patterns — 8 bearish-only + 2 dual-direction)

```
strategies/bearish/
├── double_top.py        — S1: DBL-TOP: M-pattern at resistance
├── desc_triangle.py     — S2: DESC-TRI: lower highs + flat support
├── rise_wedge.py        — S3: RISE-WEDGE: converging rising channel
├── bear_flag.py         — S4: BEAR-FLAG: consolidation after sharp drop
├── failed_breakout.py   — S5: FAILED-BO: bull trap above resistance (most reliable)
├── dead_cat.py          — S6: DEAD-CAT: bounce fade on gap-down stocks
├── open_weakness.py     — S7: OPEN-WEAK: opening weak + lower low
└── bear_engulf.py       — S8: BEAR-ENGULF: engulfing red bar at resistance

strategies/dual/
├── pin_bar.py           — S9: PIN-BAR: hammer (+1) / shooting star (-1)
└── intraday_struct.py   — S10: INTRADAY-STRUCT: HHHL (+1) / LHLL (-1)
```

Why S9 and S10 are genuinely new (not covered by existing 22):
- PIN-BAR is the only single-candle rejection pattern — all existing 22 use multi-bar logic
- INTRADAY-STRUCT is the only price-structure strategy — all existing 22 are indicator-based

Total strategies after Phase 2B: 32 (22 existing repurposed for both directions + 10 new)

### Key Architecture Changes

```
strategy_weights.json (before Phase 2B):
  { "VOL-SPIKE": 2.1, "VWAP-REV": 0.19 ... }

strategy_weights.json (after Phase 2B):
  { "VOL-SPIKE": {"long": 2.1, "short": 1.4},
    "VWAP-REV":  {"long": 0.19, "short": 0.8} ... }

composite_scorer.py (new):
  long_score  = Σ[ (signal=+1) × weight_long  × regime_modifier ]
  short_score = Σ[ (signal=-1) × weight_short × regime_modifier ]

engine.py (change):
  best_trade = max(long_candidates, short_candidates, key=abs_composite_score)
  → 1 trade/day, can be LONG or SHORT
```

### Phase 2B Sprint Plan

Workflow is **year-by-year manual triggers** — same rhythm as Phase 1/2 training.
After each training year: ask Claude to update strategy_agent.md (same as before).
After each WF freeze year: run `wf_freeze.py --window N` (1-second snapshot), then run testing.

#### Code work (before any backtesting)

| Sprint | Work | Est. Time |
|---|---|---|
| Feasibility | Analyze existing -1 signals from 2016; count profitable short opportunities | 1 day |
| Sprint 2B-1 | Implement 10 new strategies (8 bearish + PIN-BAR + INTRADAY-STRUCT) | 4–5 days |
| Sprint 2B-2 | Engine: enable -1 direction, separate long/short composite scores | 1–2 days |
| Sprint 2B-3 | weights/adaptive.py: update weight_long / weight_short independently | 1 day |
| Sprint 2B-4 | quality_filter.py: add 3 short-specific filters (8, 9, 10) | 1 day |
| Sprint 2B-5 | scripts/wf_freeze.py: freeze utility (copies weights, logs to wf_results.json) | 0.5 day |

#### Backtesting sequence (year-by-year, same manual rhythm as Phase 1/2)

```
Training 2016  → run_analysis --year 2016  → Claude writes strategy_agent.md
Training 2017  → run_analysis --year 2017  → Claude writes strategy_agent.md
Training 2018  → run_analysis --year 2018  → Claude writes strategy_agent.md
WF-1 FREEZE    → wf_freeze.py --window 1   → saves wf1_weights.json  (~1 min)
Testing  2019  → run_testing  --year 2019 --wf-window 1  → Claude writes WF-1 result

Training 2019  → run_analysis --year 2019  → Claude writes strategy_agent.md  (resumes from wf1 weights)
WF-2 FREEZE    → wf_freeze.py --window 2   → saves wf2_weights.json
Testing  2020  → run_testing  --year 2020 --wf-window 2  → Claude writes WF-2 result (COVID year)

Training 2020  → run_analysis --year 2020  → Claude writes strategy_agent.md
WF-3 FREEZE    → wf_freeze.py --window 3   → saves wf3_weights.json
Testing  2021  → run_testing  --year 2021 --wf-window 3  → Claude writes WF-3 result

Training 2021  → run_analysis --year 2021  → Claude writes strategy_agent.md
WF-4 FREEZE    → wf_freeze.py --window 4   → saves wf4_weights.json
Testing  2022  → run_testing  --year 2022 --wf-window 4  → Claude writes WF-4 result (bear year)

Training 2022  → run_analysis --year 2022  → Claude writes strategy_agent.md
WF-5 FREEZE    → wf_freeze.py --window 5   → saves wf5_weights.json  ← FINAL LIVE WEIGHTS
Testing  2023  → run_testing  --year 2023 --wf-window 5  → Claude writes partial WF-5
Testing  2024  → run_testing  --year 2024 --wf-window 5
Testing  2025  → run_testing  --year 2025 --wf-window 5
Testing  2026  → run_testing  --year 2026 --wf-window 5  → Claude writes WF-5 consolidated result

Claude evaluates WF gate (4/5 windows positive?) → writes Walk-Forward Results section in strategy_agent.md
```

Each `run_analysis` and `run_testing` trigger = 3–5 hours (same as Phase 1/2).
Total manual triggers: 7 training + 5 freezes (instant) + 8 test years = 20 steps over 4–6 weeks.

#### Final sprints

| Sprint | Work | Est. Time |
|---|---|---|
| Sprint 2B-11 | Evaluate WF gate; extend live/agent.py for short signals | 1 day |
| Sprint 2B-12 | Dashboard: direction filter + Long vs Short P&L + WF summary table | 1–2 days |

**Total: ~4–6 weeks (Walk-Forward adds ~2 weeks vs fixed split but confirms the edge is real across multiple regimes before real capital is deployed.)**

### Conflict Resolution Summary

| Situation | Resolution |
|---|---|
| Same stock: buy + sell signals | Composite score nets them; near-zero → auto-skipped by score threshold |
| Different stocks: best long vs best short | Take whichever has higher \|composite_score\| |
| Market > +1.5% up, short fires | Long score gets 1.2× tilt; short can still win if significantly stronger |
| Market < -1.5% down, long fires | Short score gets 1.2× tilt; same asymmetry |
| VIX > 20, either direction | Short score gets 1.3× (volatility historically favors shorts) |

### Memory File Decision

Extend `memory/strategy_agent.md` — do NOT create a separate strategy_agent_sell.md.
Weight table gains `wt_long` + `wt_short` + `Long Win%` + `Short Win%` + `Profile` columns.
New section "Short-Side Yearly Summary (2016–2022)" added alongside existing long-side summaries.
New section "Walk-Forward Results" records out-of-sample P&L per WF window.
Regime guidance (which strategies work in which VIX/trend) stays in ONE place.

### Walk-Forward Gate (PRIMARY gate before live deployment)

| Gate | Requirement |
|---|---|
| WF windows positive | At least 4 of 5 WF windows show positive P&L |
| WF-5 (2023–2026) | Must be positive — this is the live-period proxy |
| Combined improvement | Long + short monthly return ≥ long-only + 0.5% |
| Short standalone | Short Profit Factor ≥ 1.2 on its own |
| No drawdown increase | Adding shorts does not increase max drawdown vs long-only |

If short side fails the gate → disable shorts, proceed to Phase 3 long-only.
Phase 3 Critique Agent will veto short recommendations before real capital is risked.

*Next step after Phase 2 testing: Run Phase 2B Feasibility analysis on 2016 -1 signal logs*

"""Narrative for notebooks/05 (read by analysis/build_notebook_05.py). Keep numbers in sync with the cells."""

NARRATIVE = {}

NARRATIVE["how_it_decides"] = """
Both the backtest and live use the same machinery; the difference is **when** they are allowed to look.

1. **Watchlist** (before 09:15, history only): ~200 stocks by trend / chart patterns / liquidity.
2. **Signals**: 37 strategies each say LONG / SHORT / nothing, with an entry *level*, stop and target.
3. **Score** = sum of the *weights* of the strategies saying LONG. Live and backtest both load
   `checkpoints/wf5_weights.json`. In practice this is a **vote tally**: 21 of 37 LONG weights sit at the
   3.0 cap and 10 at 1.0, so the score is ~3 points per strong strategy. (The regime modifiers never change
   anything — VIX is hard-coded to 15 — and the NIFTY-gap bias multiplies every LONG score equally, so it never
   reorders LONG candidates.) So yes: it is essentially **signal firing + counting**, with the weights only
   separating "strong" from "weak" voters.
4. **Driver** = the voting strategy with the best *lifetime win-rate × RR*; its level/stop/target define the trade.
   Two strategies vote without an entry (ADX-FILTER, DAILY-BIAS) — they add score and agreement but never drive.
5. **Quality filters**: ≥4 agreeing strategies (lifetime LONG win-rate ≥40%), RR ≥1.5, liquidity ≥₹50 Cr/day,
   time gates (signals from 09:30 need 5 agreeing; from 10:30 a higher score), skip the 50–55% "danger zone".

| | Backtest (`backtester/engine.py`) | Live (`live/live_engine.py`) |
|---|---|---|
| bars seen | the **whole day** | only bars closed so far (every 5 min) |
| stock ranking, agreement, time gate | on the **whole day's** votes | on votes cast so far |
| entry | **at the strategy level**, at signal_time | at the live price ~3 min after the bar (scan latency) |
| extra gates | none | 30-min signal expiry, 0.30% drift gate, RR re-check, stop viability, fill gate |
| exits | target checked before stop, 15:15 | ticks, 1% stop cap, trailing lock, 14:50 |
"""

NARRATIVE["data_problems"] = """
Before comparing results, note that for much of the sample **live was not fed the same data the backtest used**:

* **Volume feed.** In **July 92% of live-built 5-min bars had zero volume** (100% on most days); from 08-10 about
  20% still did, with the volume lumped into catch-up bars (the first-hour total matches history, ~0.99×), which
  fakes volume spikes. Every volume-gated strategy (VPOC, PDH-PDL, ORB, SR-BREAK, VWAP…) voted differently live.
* **Opening bar.** The live 09:15 bar starts from the first streamed tick, not the exchange open: median
  0.20–0.25% off. Every FIRST-CANDLE level is computed from that bar.
* **Parquet time zones.** 2024–25 bars are tz-aware (+05:30), 2026 bars are tz-naive. `run_testing.py 2026`
  today would **silently drop every 2026 file** (the concat fails inside a `try/except: pass`). The June backtests
  predate the change, so historical results are unaffected — but nobody can re-run 2026 until this is fixed.
* **Duplicated backtest rows.** `paper_trades_full_history.csv` has 2025 appended twice (442 duplicate rows);
  the July divergence notebook (04) double-counted 2025. The clean WF-6 run is `paper_trades.csv`.
* **Trade-log caveat.** For PROFIT_LOCK_STOP trades, `stop_loss` in `live_paper_trades.csv` is the *final
  trailed* stop, not the original.
* **Eight configurations in three months.** The live sample mixes an early build that chased entries (to 07-13)
  with seven later rule changes — the table in section 3 splits results by the configuration in force.

The replay below uses the **historical** bars (correct volume, correct open), i.e. it answers *"what would live
have done with correct data"*.
"""

NARRATIVE["hindsight_intro"] = """
Three separate kinds of hindsight exist in `backtester/engine.py`. Section 5.1 tests the signals themselves;
5.2 the stock selection; 5.3 the entry price.
"""

NARRATIVE["causality"] = """
Each strategy was run on the full day and on the day truncated after every bar (what live sees), on 180 random
stock-days (`python -m analysis.causality_audit`). **Most signals are honest**: CAMARILLA, FIRST-CANDLE, VPOC,
RSI-EXT, BOLLINGER, MACD, SUPERTREND, PDH-PDL, CPR… are 100% causal. A minority are not: PIN-BAR, SR-BREAK,
EMA-CROSS (back-dated by a median 80 min), VWAP-REV and ORB-15/30 stamp signals earlier than they could be
known; INTRADAY-STRUCT stamps the last bar; and **ADX-FILTER votes on the *last* bar's ADX** — on a full day that
is the 15:25 ADX, i.e. "did this stock end the day in a strong uptrend". It is weight 3.0 and counts toward
agreement. (The reviewer found it gains and loses about as many votes as it adds, so its net effect is small.)
The replay recomputes all of these bar by bar.
"""

NARRATIVE["scenario_code"] = """
from analysis.scenario_specs import SPECS
R, TR = sc.run(feat, cand, SPECS, NOTIONAL)
R.to_csv(ROOT / "reports" / "gap_analysis" / "scenario_results.csv", index=False)
def cell(r):
    return "—" if not r.trades else f"{r.avg_net_pct:+.2f}% (t {r.t_stat:+.1f}, n {r.trades})"
G = R.assign(v=R.apply(cell, axis=1)).pivot_table(index="policy", columns="period", values="v", aggfunc="first", sort=False)
G = G[list(sc.PERIODS)]
G["all three > 0"] = [all(R[(R.policy == p) & (R.period == q)].avg_net_pct.fillna(-1).iloc[0] > 0 for q in sc.PERIODS) for p in G.index]
print("mean net return per trade after costs (t-stat, trades) — Rs 2L notional; sim is ~0.1%/trade optimistic vs live")
display(G)
"""

NARRATIVE["live_record"] = """
66 LONG trades, −₹37,921 as sized live (~₹5L notional). Two things to read off the tables:

* **The first ~3 weeks flatter the total.** Until 07-13 an early build chased entries at the live price and exited
  at 15:15; those 19 trades made +₹21k. Everything since has lost money, and the **current configuration (every
  gate, 14:50 exit, from 07-31) is the worst: about −0.45% of notional per trade**.
* **Stops are the whole loss**: STOP_HIT trades lose ~₹1.37L; targets and profit-locks recover part of it.
"""

NARRATIVE["pick_at_signal"] = """
For each backtest pick, the replay shows what the stock looked like at the first scan that could have seen its
signal, counting only votes cast by then. The backtest's pick typically has **~13 agreeing strategies on the full
day but only ~7 at its own entry time**, and **about a third of the picks would not have passed the quality
filters at that moment** — the backtest took them because of votes that arrived later in the day (strategies such
as STOCHASTIC, ORB-30, REL-STR — "outperformed NIFTY today" — and SR-BREAK mostly vote after the entry). That is
choosing the stock with hindsight: the reviewer found the backtest's picks rise ~+0.7% from the next bar's open to
the close in 16 of 18 months, even in a month when NIFTY fell 11%; a random liquid stock over the same window
returns about −0.05%.
"""

NARRATIVE["entry_level"] = """
The backtest buys at the strategy's *level* (e.g. the first candle's high, Camarilla H4), but the signal is only
confirmed when a bar **closes** past that level — by then the price is already beyond it. At the first scan that
could act on the signal, the price is typically **~0.2–0.3% above the level** (a quarter of picks are >0.5% above).
The backtest books every one of those trades at the level.
"""

NARRATIVE["validation"] = """
Three checks against the live session logs, split by the state of live's own data feed. The replay reproduces
live's **gate logic exactly** (re-running it on the replay's own price gives 100.00% identical verdicts on every
row), and the trade simulator reproduces **94% of live exit reasons** (per-trade P&L correlation 0.92; ~₹490/trade,
≈0.1%, optimistic because live stops fill a tick below the level). Where they differ is the *inputs*: agreement with
live's scores rises from ~30% in July (live volume feed dead) to ~56% when the feed was restored — the replay runs
on correct bars, live did not. Day-by-day picks also sit on knife edges (a 0.2% price difference flips the
viability gate; a 0.2-point win-% flips the 50–55% danger zone), so the comparison below is by distribution, not by day.

**Read the last line carefully**: on the stable-config days since 07-31, actual live lost about −0.45%/trade, while
live's own rules on correct data were roughly flat. With ~30 trades the uncertainty is ±0.3%, but it says a real part
of the recent losses came from the broken feed, on top of the edge problem below.
"""

NARRATIVE["skips"] = """
Using the replay (correct data), the first stock live "wanted" each day — passed expiry, geometry and quality, with
price still between stop and target — was **usually skipped by the drift gate** (the price had already moved ≥0.30%
past the strategy level by the time the scan decided). Live then walked down the list to a lower-ranked stock whose
price happened to still be near its level.
"""

NARRATIVE["drift"] = """
The drift gate exists to avoid chasing. Measured **causally** (price at the decision vs the level — the reviewer
caught that using the bar-mid here would peek at the bar's close), the drift buckets do not show that the trades live
takes (0–0.3%) are better than the ones it skips. Skipping on drift neither protects nor helps reliably.
"""

NARRATIVE["limit"] = """
Your idea: instead of skipping the first-pass stock when the price has run, rest a **buy limit at the strategy
level** and wait for a pull-back. The result has a trap in it: the limit fills on only ~40–60% of days, and it fills
**precisely when the breakout fails** (the price came back down to the level). The stocks that never came back —
the real breakouts — are exactly the ones a limit order misses. So the loss per trade shrinks mainly because you
trade less, not because the entries are better. The last line prices the missed stocks as if bought at market.
"""

NARRATIVE["timing_stock"] = """
Features known at the decision: NIFTY's move since its open, how far the stock had already run from its own open,
and the driver strategy. On the live-window sample the patterns are weak and noisy; section 9 tests them properly as
rules on 2025 and 2026 H1 separately (timing is tested there as "skip the first 20 / 35 minutes").
"""

NARRATIVE["scenarios_intro"] = """
Every scenario uses only information available at the decision, is priced at ₹2L per trade after costs, and is
reported separately for **2025** (used to *choose*), **2026 H1** (a check the rule was not chosen on) and the **live
window** (Jun 15 – Sep 18, the period your paper trades cover). A rule is only interesting if it is **positive in all
three** — with one trade a day, a per-trade spread of ~1% means a mean of +0.1% needs ~400 trades to reach t≈2.
The simulator is ~0.1%/trade optimistic vs live, so treat anything below ~+0.1% as zero.

Groups: **A** what live does vs taking the first-pass stock (market or your limit order) · **B** the drift gate,
both ways · **C** a NIFTY market filter · **D** dropping FIRST-CANDLE as driver · **E** exits, including your
+1% / −1% plan · **T** timing (skip the opening minutes) · **F** wait until more strategies agree.
"""

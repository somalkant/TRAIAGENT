"""Results narrative for notebooks/05 — overrides the drafts in notebook_05_narrative.py.
Every number here is printed by a cell of the notebook (run on the full 425-day replay)."""

NARRATIVE = {}

NARRATIVE["tldr"] = """
**Short version: the backtest's LONG profit was mostly hindsight. The rules live can actually run lose about
0.24% per trade — in 2025 as well as 2026 — and none of the 26 conservative variants tested makes LONG profitable.
Do not put ₹2L into this LONG system yet.**

| Your question | Answer (425 trading days, 2025-01 → 2026-09, ₹2L per trade, after costs) |
|---|---|
| Is **the stock** the problem? | **Yes — the biggest part.** The backtest chooses the stock using votes cast *later in the day*: its picks have ~13 agreeing strategies by the close but only ~7 at their own entry, and **41% would not have passed the quality filters when it "entered"**. Those late votes (STOCHASTIC, ORB, REL-STR = "outperformed NIFTY today"…) fire *because the stock went up*, so their "predictive power" is the day's outcome itself. |
| Is **the entry** the problem? | **Yes.** The backtest buys at the strategy's level, but the signal only confirms after the price has moved past it — typically +0.26% (a quarter of the time more than +0.5%). |
| | Together these two explain almost all of the **0.92%/trade gap** (backtest +0.68% → causal −0.24%). |
| Is **timing** the problem? | No. Skipping the first 20–35 minutes, waiting for more agreement, the ~3-minute scan latency — none of it changes the sign. |
| Is **the target / exit** the problem? | No. The backtest's target-before-stop is worth ~0.02%; every exit tested, including your **+1% / −1%**, lands between −0.20% and −0.26%. |
| **First-pass stock + limit order?** | It loses less per trade (−0.16% to −0.19%) only because it trades on half the days: the limit fills when the breakout **fails** (those fills win 28%, 68% get stopped) and misses the real breakouts (which would have won 59%). |
| Why did live do even worse recently? | Live was **not running the tested system**: the volume feed was dead all of July (92% of bars had zero volume) and ~20% broken after, and the 09:15 bar's open was wrong. On the stable-config days live lost −0.45%/trade; the same rules on correct data lost ~−0.07% — a small sample (±0.3%), so the feed *may have added* losses, on top of the main problem. |
| Is there a **conservative, profitable** LONG setup? | **Not in this signal set.** The best of 26 loses −0.13%/trade, which is about +0.03% *before* costs — i.e. no skill. |

**What to do** (§11): keep LONG paper trading paused and don't fund it; fix the research tool (use this causal replay
as the backtester) and live data parity; then research a **multi-day swing LONG** (decide on the previous close, enter
at the open, hold 3–10 days), where 0.16% of costs is small against the move.
"""

NARRATIVE["live_record"] = """
66 LONG trades, −₹37,921 as sized live (~₹5L notional). Two things to read off the tables:

* **The first three weeks flatter the total.** Until 07-13 an early build chased entries at the live price and exited
  at 15:15; those 19 trades made +₹21k. Everything since has lost money, and the **current configuration (every gate,
  14:50 exit, from 07-31) is the worst: about −0.45% of notional per trade** (34 trades).
* **Stops are the whole loss**: STOP_HIT trades lose ~₹1.37L; targets and profit-locks recover only part of it.
"""

NARRATIVE["pick_at_signal"] = """
For each of 401 backtest picks, the replay shows the stock at the first scan that could have seen its signal, counting
only votes cast by then. **Median agreement: 13 strategies by the close, 7 at entry time; median score 39 vs 19. 41% of
the picks would not have passed the quality filters at that moment** (mostly the 50–55% danger zone, not yet enough
agreement, or not even a scored candidate). The backtest took them because of votes that arrived later. Those late
voters (STOCHASTIC, ORB-15/30, REL-STR — literally "outperformed NIFTY today" — SR-BREAK) fire *because the stock went
up*, so the backtest was in effect picking the day's winners after the fact. The reviewer found these picks rise
~+0.7% from the next bar's open to the close in 16 of 18 months — even in a month when NIFTY fell 11% — while a random
liquid stock over the same window returns about −0.05%.
"""

NARRATIVE["entry_level"] = """
The backtest buys at the strategy *level* (the first candle's high, Camarilla H4, the VPOC…), but the signal only
confirms when a bar **closes** past that level, and live then needs ~3 minutes to scan. At the first scan that could act,
the price is **median +0.26% above the level (mean +0.36%; a quarter of the time over +0.5%, a tenth over +0.8%)**.
The backtest books every one of those trades at the level.
"""

NARRATIVE["validation"] = """
Three checks against the live session logs, split by the state of live's own data feed. The replay reproduces live's
**gate logic exactly** (re-run on the replay's own price it gives identical verdicts on all 63,000 rows checked and the
same daily pick every day); the simulator reproduces **94% of live exit reasons** (per-trade P&L correlation 0.92;
≈0.1%/trade optimistic, because live stops fill a tick below the level); and the backtest step reproduces the engine's
own exits on 100% of its picks. Where replay and live differ is the **inputs**: agreement with live's logged scores rises
from ~30% in July (live volume feed dead) to ~56% once the feed was restored — the replay runs on correct bars, live
did not. Daily picks also sit on knife edges (a 0.2% price move flips the viability gate; a 0.2-point win-% flips the
danger zone), so live and replay are compared by distribution, not day by day.

The last line: on the stable-config days since 07-31, live lost −0.45%/trade (95% CI −0.68..−0.21) while the same rules
on correct data lost ~−0.07% (35 trades; before the ~0.1% simulator optimism). With ~30 trades each this is only
~1–1.5 standard errors, so the broken feed **may have added** losses on top of the edge problem — it is not the main story.
"""

NARRATIVE["skips"] = """
On correct data, the first stock live "wanted" each day (passed expiry, geometry and quality, price still between stop
and target) was **drift-skipped on 296 of 425 days (70%)**, viability-skipped on 82 and taken on only 31. Live then
walks down the list to a lower-ranked stock whose price happens to still be near its level.
"""

NARRATIVE["drift"] = """
Measured **causally** (price at the decision vs the level; using the bar-mid here would peek at the bar's close — a bug
the reviewer caught in my first version), the bucket live takes (0–0.3%) returns −0.22%; moderate drift (0.3–1.0%)
−0.12% to −0.14%; over 1% −0.45%. No bucket is profitable: the gate does not select better trades, it just changes
which losing trade you take.
"""

NARRATIVE["limit"] = """
Your idea: instead of skipping the first-pass stock when the price has run, rest a **buy limit at the strategy level**.
The numbers show the trap: the limit fills on **46% of days**, and those fills **win only 28% (68% stopped out)** — it
fills precisely when the breakout fails and the price comes back. The days it misses are the real breakouts: bought at
market, **those would have won 59%** (+0.07% per trade). The loss per trade shrinks only because you trade less often.
"""

NARRATIVE["timing_stock"] = """
Known-at-decision features, on the first-pass stock each day. **NIFTY vs its open**: every bucket negative (best,
NIFTY above +0.2%, still −0.13%). **Run-up from the stock's own open**: negative in every bucket except over 2% (25
trades — too few to use). **Driver**: CAMARILLA −0.22%, VPOC −0.25%. (With correct volume VPOC drives almost half the
picks; live's dead volume feed silenced it — one reason live's picks differ from the replay's.) Timing is tested as
rules in §9.
"""

NARRATIVE["waterfall"] = """
Each step changes exactly one thing, on the same days, at ₹2L per trade after costs:

* **W0 → W1 honest exits** (stop-first on bars that touch both, 14:50): about −0.02%. *Exits are not the problem.*
* **W1 → W2 honest entry price** (buy after the signal confirms, not at the level): **−0.36%**.
* **W2 → W3 no hindsight in picking** (rank and filter only on votes cast so far): **−0.51%**.
* **W3 → W5 live's own gates and exits**: about −0.03% overall (helps in some periods, hurts in others).

The split between the two big steps depends on their order (W2 is measured on the hindsight picks); the robust
statement is that **together they explain almost the whole 0.92%/trade gap**, in every period. **W5 is what live can
actually do: −0.24% per trade (t −5.5) — −0.28% in 2025, −0.15% in 2026 H1, −0.26% in the live window.** It is not the
2026 market, and it matches what live actually lost (−0.25% per trade from 06-29).
"""

NARRATIVE["scenarios_read"] = """
**All 26 lose money overall; none is positive in all three periods; most are significantly negative.**

* Your **fixed +1% / −1%**: −0.23% (first-pass stock) / −0.26% (live's picks).
* Your **first-pass stock + limit at the level**: −0.19% (30 min) / −0.16% (60 min), on only about half the days.
* The reviewer's **inverted drift gate** (withdrawn after its own audit): −0.24%. **NIFTY filters**: −0.17% to −0.26%.
* **Timing** (skip the first 20 / 35 minutes): −0.19% / −0.15%. **Wait for ≥9 agreeing + NIFTY ≥ 0**: −0.13% (best).

Why no tweak works — the cost arithmetic: a round trip at ₹2L costs **0.16%** (0.10% of it assumed slippage). The best
variant, −0.13% net, is **≈ +0.03% before costs**; buying *any* liquid stock at 09:25 returns about −0.20% net (the
reviewer's universe check). The filters beat random by ~0.07%. **Once hindsight is removed, this signal set has
essentially no intraday stock-picking skill** — this is not a parameter problem.
"""

NARRATIVE["review"] = """
An independent reviewer (a separate agent, read-only on the code) went through three rounds.

**Round 1 — its own analysis of the gap.** It put the gap at 0.9–1.1%/trade (I had said 0.7%: the first June trades
came from an earlier build and flattered live), found the **dead live volume feed and the wrong 09:15 bar** (which I
then verified), showed the core CAMARILLA / first-candle breakouts lose in *every* period across ~500 stocks, and showed
that a limit at the level suffers adverse selection. It overturned three of my early claims: ADX-FILTER's hindsight vote
nets out (small), target-before-stop is worth ~0, and "don't buy stocks more than 1% above the open" does not generalise.

**Round 2 — an audit of my code.** It found a **look-ahead bug in my replay**: I used the scan bar's midpoint
(open + close)/2 as the decision price, but that bar's close only exists after the decision, so every filter selecting
on it quietly preferred bars that closed strong. It **withdrew its own "inverted drift gate" recommendation** because of
it (the gain fell from +0.24% to about +0.04% measured causally). It also found that first-pass silently dropped 25% of
days, that limit orders could fill before they existed, and that my check periods overlapped. All were fixed before the
results above; the fixed gate chain reproduces live's gates exactly.

**Round 3 — the conclusions.** It agrees with all three, with the framing adopted here: report the two big causes
together; "none of 26 specs", with the cost arithmetic; the broken feed "may have added" losses. Nothing it could find
would flip the verdict. Its one research direction: **change the horizon** (multi-day swings), because there is no
causal way to use whole-day agreement — that information arrives after the move.
"""

NARRATIVE["recommendation"] = """
**1. Don't fund the LONG system with the ₹2L.** The expected result with today's rules is about −0.24% per trade ≈
−₹480 per trade at ₹2L — roughly −₹10k a month at one trade a day; the best variant still loses ≈ −₹260 per trade. Keep
paper trading paused (it is), and put the execution-layer build on hold until there is a strategy worth executing — it
would only make these losses real.

**2. Fix the foundations** (needed for any strategy; cheap):
* Make the **backtest causal**: rank and filter on votes cast so far, enter at the next price after confirmation, stop
  before target on ambiguous bars. `analysis/replay.py` already *is* this backtester — reuse it.
* Fix the **2026 parquet time-zone bug** (the backtester silently drops 2026) and **de-duplicate** the trade history.
* **Live data parity**: repair the volume feed; build the 09:15 bar from the exchange's open/high/low, not the first tick.
* Small things the review found: NR7 never fires; slippage is charged twice in live P&L; the score thresholds in the
  time gate are dead with 3.0 weights.

**3. Research a different LONG, with a hard gate before any money.** Intraday continuation after these signals isn't
there. The most promising direction is a **multi-day swing LONG**: decide on information from the previous close (the
DAILY-BIAS trend, the chart patterns the pre-filter already detects, relative strength), enter at the next open, hold
3–10 days. Costs of 0.16% are small against 2–5% multi-day moves, and level fills, vote timing and bar parity stop
mattering. The pre-filter is already causal and history-only — a ready-made starting harness.
**Adopt a rule only if** it has the same sign in 2025, 2026 H1 and the live window with pooled t > 2, then ≥100 paper
trades on fixed data with the lower 80% confidence bound above zero — and *then* start with a fraction of the ₹2L.

*To re-run:* `python -m analysis.run_replay` (a few hours) → this notebook (a few minutes). Code in `analysis/`.
"""

# Execution Layer — Plan (v1)

Status: **planning only — no code written.** Drafted 2026-09-19 from a read of the code on `ec2-deploy` (HEAD `54247cc`),
the live paper log (126 trades, 2026-06-15 → 09-18) and the Groww SDK (`growwapi` 1.5.0).
Branch: `execution-layer`, cut from `ec2-deploy` at `ced0de2`.

Goal: turn a selected trade (`rec` from `scan_once`) into real broker orders — entry, protective stop, trail, exit —
with the same strategy/selection code above it, and with paper mode still working unchanged.

## 0. Decisions taken (2026-09-19)

| Item | Decision |
|---|---|
| Capital | **₹2,00,000** in the Groww account |
| Direction | **LONG only.** Shorts are paused — no order placing, no execution. Short signals may still be *logged*, never sent |
| Target | Fixed **+1%**; on reach, exit with a **LIMIT order at best available price** |
| Stop | **1%**, unchanged (`STOP_CAP_PCT = 1.0`) |
| Conservative window | First **30 days** |
| Email | The daily report must show **real** numbers, not paper |
| EOD & everything else | Unchanged |
| Paper trader | **Paused** (2026-09-19, `@reboot` cron for TRAIAGENT commented out on EC2) |

### ⚠️ Blocking caveat found while replaying the LONG book

A +1% cap **is** the better exit — but it does not make the LONG book profitable, so the ₹2L go-live is not yet justified
by the data. On the 36 LONG trades under today's policy (since 2026-07-29):

| | as logged | +1% cap |
|---|---|---|
| Net (5L paper size) | −₹61,599 | −₹45,704 |
| Win rate | 36.1% | 38.9% |
| Same, at ₹2L per position | −₹28,202 | −₹21,019 |

Only **10 of 36 (27.8%)** LONG trades ever reached +1%; the other 26 lost −₹83,103. Even a *perfect* +1% exit
leaves −₹45,704. With a +1% target against a −1% stop, the breakeven hit rate is **45.9%** and the live rate is
**27.8%** → expectancy **−0.286% of notional per trade**. Projected over ~22 trades in 30 sessions at ₹2L:
**−₹12,845 (−6.4% of the account)**, 1sd band −₹20,741 … −₹4,950 — i.e. essentially every outcome is a loss.

**No take-profit level fixes this.** Sweeping the target from 0.30% to 2.00%, holding entry, size, stop and the
eventual exit unchanged (so every simulated exit lies inside the observed price path):

| target | 0.30% | 0.50% | 0.75% | **0.85%** | 1.00% | 1.50% | 2.00% | as-is |
|---|---|---|---|---|---|---|---|---|
| all 66 LONG | −55,507 | −45,658 | −28,161 | **−21,032** | −23,798 | −33,357 | −56,011 | −37,921 |
| era C (36) | −48,379 | −42,656 | **−30,552** | −31,228 | −45,704 | −60,698 | −61,599 | −61,599 |

The curve is a shallow U with its floor around 0.75–0.85%, and **the floor is still a loss** (−₹12,007 at ₹2L
per position on the full sample; −₹14,970 on era C). Low targets are hit often but a 0.30% gross win nets only
~0.15% after costs while the losers still give up ~1%; high targets almost never trigger. The reason is the
underlying move size: the median LONG trade runs just **+0.69%** in our favour (**+0.59%** in era C), and only
27.8% of era-C trades reach +1% at all.

Method validation: bar-derived MFE ≥ 1% agreed with the live `profit_locked` flag on **100% of 46** trades where
both exist; MFE came from bars for 64 of 66 trades (the 2 exceptions are ~2-minute trades inside a single bar).

**Conclusion: build stages 0–3 (they make the paper run honest and cost nothing), but entry selection has to
improve before real money goes in. The execution layer changes how orders reach the market, not the edge — and
neither does the target. This is an entry-quality problem.**

---

## 1. Where the code stands

Everything below `scan_once` is simulated. There is **no order code anywhere** (`BaseBroker` covers auth, credentials and
data classes only; `grep place_order` finds nothing).

| Paper behaviour today | Where | Why it will not survive real money |
|---|---|---|
| Entry = instant book-walk fill at signal time, booked at crossed-spread price | `live_engine.py` fill gate, `agent.py` `PAPER TRADE PLACED` | Real orders take time, partially fill, get rejected. `_settle_fills` only *simulates* the +5 min outcome |
| Stops are **virtual**: evaluated on ticks + a 3 s REST poll; nothing rests at the broker | `_check_exit`, `_position_price_loop` | Agent/feed/EC2 dies → position is unprotected. 14 Sep: Groww NATS feed dead 09:37 → 14:50 (no position was open, luck) |
| Exit booked at the book price at decision time | `_check_exit`, `_force_time_exit` | Real fill lags the decision and can be worse (see §2) |
| Restart memory = only the *open* trades (`live_open_trade.json`); "already traded today" flags are not saved | `paper_logger.save_open_trade`, `agent.main` step 6 | After a restart the agent can re-enter. Seen live: same-direction repeats on 06-15, 06-24 (JSWSTEEL ×3), 06-29. Fix `2fbcb01` exists only on `main` |
| Daily loss limit (₹40k) is checked at startup and EOD only | `risk_guard.py` | Nothing stops trading intraday |
| Broker-agnostic layer has no order methods | `brokers/base.py` | New interface needed |

## 2. What the live paper data says about execution realism

- **Exits are optimistic.** Of the 86 exits where the book could be verified, 18 (21%) were flagged `EXIT_NOT_FILLED`/`PARTIAL`
  — for stop exits, 10 of 36 (28%). Booked stop overshoot is ~0 (median 0.00%, max 0.17%), which a real stop order will not match.
- **Stops are the whole P&L story:** `STOP_HIT` 52 trades = −₹2,66,625; everything else nets +₹1,29,589. Median stop hold 66 min; 35% stop out within 30 min.
- **Notional is the cap, not risk:** median position ₹4.99L (the ₹5L cap binds), two legs/day ≈ ₹10L notional.

**Go-live context (blunt):** live paper is −₹1,37,036 over 126 trades (38.9% win rate, 20 of 66 sessions green; shorts −₹99k, longs −₹38k).
Since the 1% stop cap went live (07 Sep): 9 sessions, 18 trades, −₹27,011 (small sample, but not encouraging).
The execution layer changes *how* orders reach the market, not the expectancy. So: build stages 1–3 regardless (they are safe and
make the paper run more honest); **stage 4 (real money) is gated on a decision you make with the data, not on the calendar.**

## 3. Design principles (invariants the code must enforce)

1. **Journal before send.** Every order intent is written to a durable journal *before* the broker call, keyed by a client
   `order_reference_id`. A restart or an ambiguous timeout can look the order up by reference (`get_order_status_by_reference`)
   instead of re-sending. Also persists "placed/closed today" so restart cannot double-enter.
2. **Broker is the source of truth for positions.** Reconcile against `get_positions_for_user` at startup, every ~30 s, and after every exit.
3. **Never exit more than the broker says is open** (reduce-only guard). Prevents a stop + agent exit double-firing and flipping a short into a long.
4. **No unprotected fill.** A filled position gets a protective stop for the *filled* qty within seconds, or is flattened.
5. **Fail safe = flatten, not hold.** Unknown state (reconcile mismatch, dead feed with open position, repeated rejects) → alert, cancel resting orders, flatten.
6. **Human arms live trading each day.** The agent auto-starts on `@reboot` cron; a reboot must never silently trade real money.
   Live requires `EXECUTION_MODE="live"` **and** a dated `checkpoints/LIVE_ARMED.flag` created that morning. Kill switch = a flag file (same idiom as `HALT_*.flag`).
7. **Strategy never talks to the broker.** Interface is `OrderIntent` in, fill events out.

## 4. Architecture

New package `execution/` (nothing in it imports strategy code):

| Module | Job |
|---|---|
| `models.py` | `OrderIntent`, `Order`, `Fill`, `Position`, order-state enum (table-driven — see §7, status strings unknown) |
| `broker_api.py` | `BrokerOrderAPI` ABC: place / modify / cancel / status_by_ref / trades / positions / margin. Impls: `GrowwOrders` (wraps the raw `GrowwAPI` already held in `GrowwClientAdapter._client` — same token), `SimBroker` (wraps today's `simulate_fill`, so **paper runs the same executor path**), later `ZerodhaOrders` |
| `journal.py` | Append-only JSONL `checkpoints/orders_YYYY-MM-DD.jsonl` + replay on start |
| `executor.py` | Per-leg state machine: `INTENT → ENTRY_SENT → (PARTIAL/FILLED/REJECTED/TIMEOUT→cancel) → PROTECTED → MANAGING → EXIT_REQUESTED → EXIT_SENT → FLAT`; any state → `HALTED` |
| `reconciler.py` | Broker positions vs journal vs `AgentState`; mismatch → alert + flatten |
| `risk_gate.py` | Pre-send checks: kill switch, armed flag, intraday P&L (realised + MTM) vs `DAILY_LOSS_LIMIT`, max qty/notional, limit-price band vs LTP, dup check, margin available, order-rate limiter |
| `notifier.py` | Alerts through the SMTP path already used by `live/email_report.py` |

Surgical hooks in existing code (each behind `EXECUTION_MODE`; `paper` = today's behaviour):

- `agent._run_market_loop`: replace `PAPER TRADE PLACED` + `check_fill` with `executor.submit_entry(rec)`.
- `agent._check_exit` / `_force_time_exit`: replace `close_fn(rec)` + `log_closed_trade(exit_price=ref_price)` with `executor.submit_exit(rec, reason)`; book the **actual average exit fill**.
- `agent._update_profit_lock`: after the stop ratchets, `executor.modify_stop(rec, new_stop)`.
- `paper_logger.log_closed_trade`: already honours `_avg_fill_price`; add `mode`, `order_ids`, `entry_slip`, `exit_slip` columns.
- `risk_guard`: add an intraday check (called by the risk gate).

## 5. Decisions needed from you (with my recommendation)

| # | Decision | Status | Why |
|---|---|---|---|
| D0 | **Base branch.** `ec2-deploy` and `main` have diverged (31 vs 13 commits) | **Open** — building on `ec2-deploy`; still need to merge `main` or cherry-pick `2fbcb01` | `2fbcb01` fixes restart re-entry; without it a restart can re-enter a symbol |
| D1 | Live broker | **Groww** (settled) | Data feed, instruments and token already there; Zerodha's live path has never run |
| D2 | Entry order type | **Marketable LIMIT** at book-cross price, capped by `FILL_SLIP_GATE_PCT` (0.20%), cancel if unfilled after ~20–30 s; partial fill → keep filled qty, cancel rest, size stop to filled qty. Never plain MARKET | Reuses the fill-gate logic already validated in paper; bounds slippage |
| D3 | **Protective stop design** | **Open.** Recommend a resident **backstop** wider than the virtual stop (~1.5×) while the virtual book-corroborated logic stays primary | A resident stop triggers on trade prints and would reintroduce the single-print wick stop-outs `_exit_ref_price` exists to filter |
| D4 | Pilot scope | **LONG only, ₹2L, +1% target / 1% stop, 30 days** (settled) — but see the blocking caveat in §0 | Shorts are the weaker side (−₹99k) and add margin/circuit complexity |
| D5 | Real capital | **₹2,00,000** (settled). At 2L a position is ~179 shares vs 449 in paper; round-trip brokerage is 0.020% of notional vs 0.008% | Re-cost every comparison at 2L — the ₹5L paper P&L flatters the pilot |
| D6 | Infra for live | Scheduled instance start (EventBridge) + Elastic IP + "agent not up by 09:10" alert | Nothing auto-starts the box today; public IP changes each stop/start |
| D7 | **Email shows real numbers** | `live/email_report.py` must read the live-order book, label the mode, and never mix paper and real rows in one total | Explicit requirement; a mislabelled report is worse than none |

## 6. Rollout

| Stage | What | Exit criteria |
|---|---|---|
| 0 | **Read-only prereq checks** (no orders): entitlement, margin, MIS + shorting support, SL/SL-M availability, static-IP rule, rate limits | Answers to every item in §7 |
| 1 | Build `execution/` with `SimBroker` + journal + reconciler + risk gate; wire behind `EXECUTION_MODE=paper` | Paper output matches current logic on replay; failure-injection tests pass (timeout, partial fill, reject, duplicate ack, restart mid-order, cancel-vs-fill race, feed death) |
| 2 | **Shadow**: real quotes + `get_order_margin_details`, log the orders that *would* be sent beside paper fills | ~10 sessions, no unexplained diffs |
| 3 | **Broker smoke test**: 1-share orders on a liquid name — place/modify/cancel, order-update stream, reject reasons | Documented status table; measured place→ack→fill latency (p50/p95) |
| 4 | **Pilot live** (D4 scope), armed daily, kill-switch drill on day 1 | You sign off after N sessions with zero reconcile mismatches and realised-vs-paper slippage inside tolerance |
| 5 | Scale-up | Data-driven, separate decision |

## 7. Unknowns to verify (do not assume)

- **Groww order-status vocabulary** — SDK defines only smart-order statuses; get real strings from the smoke test, keep the state machine table-driven.
- **`order_reference_id` format constraints** (SDK default is a random 8-digit number — collision-prone, so we supply our own).
- **Rate limits** — SDK raises `GrowwAPIRateLimitException` on 429 but documents no numbers.
- **Order-update stream**: `GrowwFeed.subscribe_equity_order_updates` exists → fast path for fills, but it rides the same NATS transport that died on 14 Sep, so **REST polling by reference every ~2 s stays the authority**.
- **MIS equity shorting** on Groww, **SL vs SL-M** for cash MIS (if only SL-limit exists, a stop can gap through its limit), broker auto-square-off time and fee.
- **Static-IP whitelisting** for order APIs under the current retail-algo rules — check Groww's rule for our account.
- **Key scope & storage**: `GROWW_API_TOKEN` + TOTP secret sit in `.env` on EC2; once the token can place orders that file holds money authority. Check key scopes, EC2 security-group inbound rules, consider SSM Parameter Store.

## 8. Immediate next steps

1. **Decide on §0's caveat**: the LONG book loses money even with a perfect +1% exit. Either
   (a) hold real money back and work on entry selection, or (b) go live at a deliberately small
   size treating the cost as tuition. Not my call, but (a) is what the data supports.
2. Answer D0 (merge `main` / cherry-pick `2fbcb01`) and D3 (stop design).
3. Stage 0 read-only checks on EC2 (profile, margin, instrument lookup — no orders). Needs your OK since it uses the live token.
4. Stage 1 scaffolding (`models`, `journal`, `SimBroker`, `FakeBroker` + tests) — **not wired into the live agent until you approve.**

## 9. Appendix — how the +1% replay was done

`profit_locked` in the trade log is set the instant observed MFE ≥ 1.0%, so it is a live-tick-ordered
record that price actually reached +1% — stronger evidence than 5-min bar replay, which cannot resolve
intra-bar ordering. But it is only trustworthy from **2026-07-15** (profit-lock shipped in `cf8635a`
on 07-14); before that the flag is silent, not False. Those 20 earlier LONG trades were replayed against
their entry-day 5-min bars instead. Ride-past-target shipped **2026-07-29** (`01378ba`), so only trades
from that date compare like-for-like against today's policy — hence the era split. Two very short trades
(CIPLA 06-29, APOLLOHOSP 07-13, both ≈2 min) fell inside a single bar and fell back to their booked exit.
Script: `scratchpad/long_replay2.py`, per-trade output `long_replay2.csv`.

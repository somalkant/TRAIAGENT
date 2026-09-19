"""
Builds notebooks/05_live_vs_backtest_gap_LONG.ipynb.

    venv\\Scripts\\python.exe -m analysis.build_notebook_05

The narrative (markdown) is kept here next to the code so the two can't drift apart; numbers quoted
in the narrative are the ones the code cells print when run on reports/gap_analysis/replay/.
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "05_live_vs_backtest_gap_LONG.ipynb"
NARR = ROOT / "analysis" / "notebook_05_narrative.py"

cells: list = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip("\n")))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip("\n")))


def build(narr: dict) -> None:
    N = lambda k: narr.get(k, f"*(narrative `{k}` pending)*")

    md(f"""
# 05 · Live vs backtest — where the LONG edge goes, and what could make LONG profitable

**Question.** The backtest said LONG makes ~+0.7% of notional per trade. Three months of live paper
trading lost money. Is it the entry, the timing, the stock, or the exits — and is there a *conservative*
LONG configuration that is actually profitable?

**Scope.** LONG only (shorts are paused). All money figures are at **₹2,00,000 per trade** (the planned live
capital), after brokerage, STT, exchange, GST, stamp duty and 0.05%/side slippage.

**Data.** Live paper trades 2026-06-15 → 09-18 (66 LONG), every live entry decision from the session logs
(06-29 → 09-18), 5-min bars for ~500 stocks, and a **causal replay** of the live entry logic on 426 trading
days (2025-01 → 2026-09) — what live would have done each day, using only bars that existed at the time.

**How to run.** Kernel *TRAIAGENT (venv)*. The replay is precomputed in `reports/gap_analysis/replay/`
(re-create with `python -m analysis.run_replay`, ~hours). This notebook then runs in a few minutes.
""")
    md("## 0 · Answers\n\n" + N("tldr"))

    md("## 1 · Setup")
    code("""
import sys, warnings
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT)); warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import plotly.graph_objects as go
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 80)

from analysis import report as rep
from analysis.live_log_parser import load_decisions, first_pass_candidates
from analysis.policies import (load_replay, trades_from_rows, bt_trades, pick_live, pick_first_pass, summarize,
                               ExitRule, LIVE_EXIT, BT_EXIT, REAL_BT_EXIT)
from analysis.gap import waterfall
from analysis import scenarios as sc
from analysis.validate import validate

NOTIONAL = 200_000
L   = rep.live_long()                                 # live LONG paper trades
dec = load_decisions(ROOT / "logs" / "ec2")           # every logged live entry decision
bt, cand = load_replay()                              # backtest picks + causal live-replay candidates
print(f"live LONG trades: {len(L)} ({L.date.min():%Y-%m-%d} -> {L.date.max():%Y-%m-%d})")
print(f"logged decision events: {len(dec):,} over {dec.date.nunique()} sessions")
print(f"replay: {cand.date.nunique()} days ({cand.date.min():%Y-%m-%d} -> {cand.date.max():%Y-%m-%d}), "
      f"{len(cand):,} candidate rows, {len(bt)} backtest picks")
""")

    md(f"""
## 2 · How the LONG decision is actually made

{N("how_it_decides")}
""")
    code("""
import json
w = json.load(open(ROOT / "checkpoints" / "wf5_weights.json"))
wl = pd.Series({k: v["long"] for k, v in w.items()}).round(3)
print("LONG weight values (count of strategies):", wl.value_counts().sort_index(ascending=False).to_dict())
from weights.regime import get_regime_modifiers
print("regime modifiers at VIX=15 (VIX is hard-coded to 15):",
      {k: v for k, v in get_regime_modifiers(w, vix=15.0).items() if v != 1.0} or "all 1.0 — inert")
""")

    md(f"""
## 3 · The three-month live LONG record

{N("live_record")}
""")
    code("""
print("By month"); display(rep.by(L, "month"))
print("By exit reason"); display(rep.by(L, "exit_reason"))
print("By live configuration in force (the sample mixes 8 configurations)"); display(rep.by(L, "era"))
fig = go.Figure(go.Scatter(x=L.date, y=L.sort_values("date").pnl_rs.cumsum(), mode="lines+markers"))
fig.update_layout(title="Live LONG cumulative P&L (paper, as sized live)", height=320, template="plotly_white")
fig.show()
""")

    md(f"""
## 4 · Live was not running the backtested system — data problems

{N("data_problems")}
""")
    code("""
H = rep.live_candle_health(); H["month"] = H.date.str[:7]
print("Live-built 5-min bars with ZERO volume (to 11:00), by month:")
display(H.groupby("month").agg(sessions=("date", "size"), zero_volume_pct=("zero_volume_pct", "mean")).round(1))

import pandas as pd
for y in (2025, 2026):
    d = pd.read_parquet(ROOT / "data" / "stocks" / str(y) / "TECHM.parquet", columns=["datetime"])
    print(f"{y} parquet datetime dtype: {d.datetime.dtype}")
print("-> backtester.engine._preload_data concatenates the two inside try/except: the 2026 file is silently dropped.")

full = pd.read_csv(ROOT / "data" / "trade_logs" / "ec2_snapshot" / "paper_trades_full_history.csv", low_memory=False)
print(f"paper_trades_full_history.csv: {len(full)} rows, {full.duplicated(['date','symbol','direction']).sum()} duplicated (date, symbol, direction)")
""")

    md(f"""
## 5 · Where the backtest sees the future

{N("hindsight_intro")}

### 5.1 Are the strategies' signals causal?
{N("causality")}
""")
    code("""display(rep.causality_table())""")
    md(f"""
### 5.2 Did the backtest's pick even qualify at its own signal time?
{N("pick_at_signal")}
""")
    code("""
X = rep.bt_pick_at_signal_time(bt, cand)
X = X[X.scan <= "11:00"]
print(f"backtest picks with signal <= 10:55: {len(X)}")
print(f"  full-day agreeing strategies: median {X.full_day_agreeing.median():.0f} | at signal time: median {X.agreeing_then.median():.0f}")
print(f"  full-day score:               median {X.full_day_score.median():.1f} | at signal time: median {X.score_then.median():.1f}")
print(f"  would NOT have passed the quality filters at their own signal time: {100*(~X.quality_then).mean():.0f}%")
print("  why they fail at signal time:"); display(X[~X.quality_then].reason_then.str.replace(r"[\\d.]+", "#", regex=True).value_counts().head(6))
""")
    md(f"""
### 5.3 Entry at the level vs the price you can actually get
{N("entry_level")}
""")
    code("""
T_lvl = bt_trades(bt, "bt_level", REAL_BT_EXIT, NOTIONAL)
T_mkt = bt_trades(bt, "market", REAL_BT_EXIT, NOTIONAL)
print(f"price at the first scan that could see the signal vs the strategy level (backtest picks):")
print(T_mkt.drift_pct.describe(percentiles=[.25, .5, .75, .9]).round(3).to_string())
""")

    md(f"""
## 6 · Is the replay faithful to live?

{N("validation")}
""")
    code("""
per = {"Jul (live volume feed dead)": ("2026-06-29", "2026-07-31"), "Aug 03-07 (volume restored)": ("2026-08-01", "2026-08-09"),
       "Aug 10+ (~20% zero-volume bars)": ("2026-08-10", "2026-09-18")}
rows = []
for name, (a, b) in per.items():
    c = cand[(cand.date >= a) & (cand.date <= b)]
    v = validate(c, dec[(dec.date >= a) & (dec.date <= b)])
    rows.append({"period": name, "days": c.date.nunique(),
                 "score exact %": v["inputs"]["score_exact"], "agreement exact %": v["inputs"]["agreeing_exact"],
                 "PASS/FAIL same %": v["inputs"]["pass_fail_same"], "same gate %": v["gates"]["same_gate_pct"],
                 "level exact %": v["gates"]["level_exact_pct"], "same stock %": v["picks"]["same_stock_pct"]})
display(pd.DataFrame(rows).set_index("period"))
""")
    code("""
# Distribution check: replay 'live rules' vs actual live, same days, same exits, Rs 2L
live_days = L[L.date >= "2026-07-31"]
rep_live = trades_from_rows(pick_live(cand[(cand.date >= "2026-07-31")]), "market", LIVE_EXIT, NOTIONAL)
act = live_days.assign(net_pct=live_days.pnl_rs / live_days.notional * 100)
se = act.net_pct.std() / np.sqrt(len(act))
print(f"actual live (stable config, from 07-31): n={len(act)}  mean {act.net_pct.mean():+.3f}%/trade (95% CI {act.net_pct.mean()-1.96*se:+.2f}..{act.net_pct.mean()+1.96*se:+.2f})  win {100*(act.pnl_rs>0).mean():.0f}%")
s_ = summarize(rep_live, "replay")
print(f"replay of live's rules on CORRECT data:  n={s_['trades']}  mean {s_['avg_net_pct']:+.3f}%/trade (t {s_['t_stat']:+.2f})  win {s_['win_pct']:.0f}%")
""")

    md(f"""
## 7 · The gap, step by step

{N("waterfall")}
""")
    code("""
W, steps = waterfall(bt, cand, NOTIONAL)
per = {**sc.PERIODS, "ALL 2025-01..2026-09": (None, None)}
rows = []
for k, t in steps.items():
    for p, (a, b) in per.items():
        tt = t if a is None else t[(t.date >= a) & (t.date <= b)]
        rows.append({"step": k, "period": p, **{kk: vv for kk, vv in summarize(tt, k).items() if kk != "policy"}})
WF = pd.DataFrame(rows)
display(WF.pivot_table(index="step", columns="period", values="avg_net_pct", sort=False))
display(WF[WF.period == "ALL 2025-01..2026-09"].set_index("step").drop(columns="period"))
""")

    md(f"""
## 8 · The entry decision: which stock, when, and at what price

### 8.1 What live skipped, and what the skipped stocks did
{N("skips")}
""")
    code("""
feat = sc.add_features(cand, cache=ROOT / "reports" / "gap_analysis" / "features.parquet")   # tradeable candidates + causal features
first = pick_first_pass(cand)
gate_of_first = first.gate_c.value_counts()
print("first quality-passing candidate each day — what live's gates did with it:"); display(gate_of_first)
""")
    md(f"""
### 8.2 The drift gate — does skipping 'chased' prices help?
{N("drift")}
""")
    code("""
fp = feat.sort_values(["date", "scan", "rank"]).groupby("date").head(1)
T = trades_from_rows(fp, "market", LIVE_EXIT, NOTIONAL)
T["net_pct"] = T.pnl / (T.entry * T.qty) * 100
T["drift_bkt"] = pd.cut(T.drift_pct, [-5, 0, 0.3, 0.6, 1.0, 5], labels=["<=0 (at/below level)", "0-0.3 (live takes)", "0.3-0.6", "0.6-1.0", ">1.0"])
print("drift measured CAUSALLY (scan bar's open vs the strategy level); entry at bar-mid; live exits")
display(T.groupby("drift_bkt", observed=True).agg(trades=("pnl", "size"), win_pct=("pnl", lambda x: round(100*(x>0).mean(),1)),
        avg_net_pct=("net_pct", "mean"), net_rs=("pnl", "sum")).round(3))
""")
    md(f"""
### 8.3 Your idea: take the first-pass stock with a LIMIT order at the strategy level
{N("limit")}
""")
    code("""
lim = trades_from_rows(fp, "limit", LIVE_EXIT, NOTIONAL, limit_window_bars=6)
mkt = trades_from_rows(fp, "market", LIVE_EXIT, NOTIONAL)
print(f"first-pass candidates: {len(fp)} | limit filled within 30 min: {len(lim)} ({100*len(lim)/len(fp):.0f}%)")
display(pd.DataFrame([summarize(mkt, "first-pass, market"), summarize(lim, "first-pass, limit at level (30 min)")]))
filled = set(zip(lim.date, lim.symbol)); unf = mkt[[ (d, s) not in filled for d, s in zip(mkt.date, mkt.symbol)]]
display(pd.DataFrame([summarize(unf, "…the ones the limit MISSED, had you bought at market")]))
""")
    md(f"""
### 8.4 Timing and stock features
{N("timing_stock")}
""")
    code("""
T = trades_from_rows(fp, "market", LIVE_EXIT, NOTIONAL).merge(fp[["date", "symbol", "runup_pct", "nifty_now_pct", "vwap_pct"]], on=["date", "symbol"])
T["net_pct"] = T.pnl / (T.entry * T.qty) * 100
def tab(col, bins, labels):
    T["b"] = pd.cut(T[col], bins, labels=labels)
    return T.groupby("b", observed=True).agg(trades=("pnl", "size"), win_pct=("pnl", lambda x: round(100*(x>0).mean(),1)), avg_net_pct=("net_pct", "mean")).round(3)
print("by NIFTY vs its open at the scan"); display(tab("nifty_now_pct", [-9, -0.2, 0, 0.2, 9], ["< -0.2%", "-0.2..0", "0..+0.2", "> +0.2%"]))
print("by stock run-up from its open");     display(tab("runup_pct", [-9, 0, 0.5, 1, 2, 9], ["< 0", "0-0.5", "0.5-1", "1-2", "> 2"]))
print("by driver"); display(T.groupby("driver").agg(trades=("pnl", "size"), avg_net_pct=("net_pct", "mean")).round(3).sort_values("trades", ascending=False).head(8))
""")

    md(f"""
## 9 · Scenarios — is there a conservative LONG configuration that makes money?

{N("scenarios_intro")}
""")
    code(narr.get("scenario_code", "# scenario grid pending"))
    md(N("scenarios_read"))

    md(f"""
## 10 · Independent review (subagent) — where we agree and disagree

{N("review")}
""")
    md(f"""
## 11 · Recommendation

{N("recommendation")}
""")


if __name__ == "__main__":
    narrative: dict = {}
    for f in (NARR, NARR.with_name("notebook_05_conclusions.py")):     # conclusions override drafts
        if f.exists():
            ns: dict = {}
            exec(f.read_text(encoding="utf-8"), ns)
            narrative.update(ns.get("NARRATIVE", {}))
    build(narrative)
    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"]["kernelspec"] = {"name": "traiagent", "display_name": "TRAIAGENT (venv)", "language": "python"}
    OUT.write_text(nbf.writes(nb), encoding="utf-8")
    print(f"wrote {OUT} ({len(cells)} cells)")

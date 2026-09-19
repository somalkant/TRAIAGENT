"""
Builds notebooks/06_causal_LONG_2025.ipynb and notebooks/07_causal_LONG_2026.ipynb.

    venv\\Scripts\\python.exe -m analysis.build_causal_notebooks
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
MONTHS = {2025: [f"2025-{m:02d}" for m in range(1, 13)], 2026: [f"2026-{m:02d}" for m in range(1, 10)]}
NAMES = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July", 8: "August",
         9: "September", 10: "October", 11: "November", 12: "December"}


def build(year: int) -> Path:
    cells = []
    md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip("\n")))
    code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip("\n")))
    num = "06" if year == 2025 else "07"

    md(f"""
# {num} · LONG paper trades {year} — the fixed system, simulated left to right

Every trading day of {year} is replayed the way the live system would have run it, **one 5-minute bar at a
time**, and every trade is shown with the chart the system was looking at when it entered, and what happened next.

**No look-ahead — how it is guaranteed** (`backtester/causal_engine.py`)
* Each day starts with only history (the pre-market watchlist uses days before today).
* Bars are released from the parquet files **one at a time**; at each bar close every strategy is recomputed on
  the bars released so far — nothing is ever computed on the full day.
* Stocks are ranked on the votes cast *so far*; the entry is the close of the bar that confirmed the signal.
* After entry the position is managed on the bars that follow, one at a time (stop checked before target inside a bar).
* Section 1 **proves** it: sample days are re-run with every bar after the decision **deleted** — the trade must come
  out identical — and every trade is checked for signal ≤ decision bar < entry < exit.

**The system as it runs live, with these fixes** (all in `Config` below; change them and re-run)
| | Fixed version (this notebook) | Live today |
|---|---|---|
| stock choice | votes cast so far (like live) | same |
| entry | **at the close of the bar that confirmed the signal** | ~3 min later, after the scan |
| drift gate ("don't chase") | **off** — take the trade | skips if price ≥0.30% past the level |
| stop | **1%** (strategy stop, never farther than 1%) | same |
| target / exit | strategy target, trailing lock (+1% → trail 0.5%), square-off 14:50 | same |
| fill | **at the chosen price, full size** (liquid stocks) | book walk |
| trades | 1 LONG per day, ₹2,00,000 | same (paper sized ~₹5L) |

Costs: brokerage, STT, exchange, SEBI, GST and stamp duty; slippage 0 (section 2 also shows 0.05% per side).

**Running it**: kernel *TRAIAGENT (venv)*. The first run simulates the year on 8 worker processes
(~30–60 min) and caches each day in `reports/causal/`; later runs load the cache in seconds. Data is read from
`data/stocks/` and `data/index/` through `data_pipeline.bars.normalize_bars` (session bars 09:15–15:25, IST).
""")
    code(f"""
import sys, warnings
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT)); warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from datetime import date
from backtester.causal_engine import Config, run_period, trades_frame, verify_no_lookahead, costs
from analysis import trade_charts as tc
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 80)

YEAR = {year}
CFG = Config()            # e.g. Config(drift_gate_pct=0.30) for live's gate, Config(weights="uniform") for no weights
display(pd.Series(CFG.__dict__, name="config").to_frame())
END = date(YEAR, 12, 31) if YEAR < 2026 else date(2026, 9, 18)
res = run_period(date(YEAR, 1, 1), END, CFG, workers=8)
T = trades_frame(res)
T["net_pct"] = T.pnl_rs / (T.entry * T.qty) * 100
print(f"{{len(res)}} trading days simulated, {{len(T)}} trades")
""")

    md("""
## 1 · Proof there is no look-ahead

**Re-run test**: for a random sample of traded days, the whole day is simulated again with **every bar after the
decision bar deleted from the data**. If any decision had used a later bar, the stock, entry time or entry price
would change. **Ordering test**: for every trade, the signal bar ≤ the last bar the decision used < the entry time
< the exit time.
""")
    code("""
V = verify_no_lookahead(res, CFG, sample=15)
display(V)
assert V.identical.all(), "a decision changed when future bars were removed — look-ahead!"
hm = lambda s: int(s[:2]) * 60 + int(s[3:5])
ok = T.apply(lambda t: hm(t.signal_time) <= hm(t.decision_bar) < hm(t.entry_time) <= hm(t.exit_time), axis=1)
assert ok.all(), T[~ok]
print(f"re-run test: {V.identical.sum()}/{len(V)} identical | ordering test: all {len(T)} trades pass")
""")

    md("## 2 · The year in numbers")
    code("""
n = len(T); m = T.net_pct.mean(); se = T.net_pct.std() / np.sqrt(n)
eq = T.sort_values("date").pnl_rs.cumsum()
print(f"trades {n} | winners {100*(T.pnl_rs>0).mean():.1f}% | net ₹{T.pnl_rs.sum():+,.0f} at ₹2L per trade | "
      f"mean {m:+.3f}% per trade (t {m/se:+.2f}) | worst drawdown ₹{(eq - eq.cummax()).min():,.0f}")
slip = T.apply(lambda t: t.pnl_rs - costs(t.entry*t.qty, t.exit*t.qty, 0.05) + costs(t.entry*t.qty, t.exit*t.qty, 0.0), axis=1)
print(f"with 0.05% slippage per side instead of 0: net ₹{slip.sum():+,.0f} ({(slip / (T.entry*T.qty) * 100).mean():+.3f}% per trade)")
print(f"days with no LONG trade: {sum(1 for r in res if not r.get('trade'))} of {len(res)}")
print("\\nby month"); display(tc.month_table(res))
print("by exit reason"); display(T.groupby("exit_reason").agg(trades=("pnl_rs","size"), net_rs=("pnl_rs","sum"), avg_net_pct=("net_pct","mean")).round(2))
print("by driver strategy"); display(T.groupby("driver").agg(trades=("pnl_rs","size"), win_pct=("pnl_rs", lambda x: 100*(x>0).mean()), net_rs=("pnl_rs","sum"), avg_net_pct=("net_pct","mean")).round(2).sort_values("trades", ascending=False))
print("by entry time"); T["entry_slot"] = pd.cut(T.entry_time.map(hm), [0, 570, 585, 600, 660, 900], labels=["09:20-09:30", "09:35-09:45", "09:50-10:00", "10:05-11:00", "after 11:00"])
display(T.groupby("entry_slot", observed=True).agg(trades=("pnl_rs","size"), win_pct=("pnl_rs", lambda x: 100*(x>0).mean()), avg_net_pct=("net_pct","mean")).round(2))
fig, ax = plt.subplots(figsize=(12, 3.2), dpi=80)
ax.plot(pd.to_datetime(T.sort_values("date").date), eq.values, color="#1565c0"); ax.axhline(0, color="grey", lw=0.8)
ax.set_title(f"{YEAR} cumulative net P&L, ₹2L per trade"); plt.show()
""")

    if year == 2026:
        md("""
### Compared with what live actually traded (Jun 15 – Sep 18)
Same days, same rules except the fixes above. Live's own P&L is as sized live (~₹5L); the fixed system's is at ₹2L.
Differences in the stock picked come from live's broken inputs (volume feed, opening bar), live's drift gate and
~3-minute scan delay.
""")
        code("""
L = pd.read_csv(ROOT / "data" / "trade_logs" / "live_paper_trades.csv", parse_dates=["date"])
L = L[L.direction == "LONG"][["date", "symbol", "entry_time", "entry_price", "exit_reason", "pnl_rs"]]
L["date"] = L.date.dt.strftime("%Y-%m-%d")
C = T[T.date >= "2026-06-15"][["date", "symbol", "entry_time", "entry", "exit_reason", "pnl_rs", "net_pct"]]
cmp_ = L.merge(C, on="date", how="outer", suffixes=("_live", "_fixed")).sort_values("date")
cmp_["same_stock"] = cmp_.symbol_live == cmp_.symbol_fixed
display(cmp_)
print(f"same stock on {cmp_.same_stock.sum()} of {cmp_.date.nunique()} days | live net ₹{cmp_.pnl_rs_live.sum():+,.0f} (at ~₹5L) | "
      f"fixed system net ₹{cmp_.pnl_rs_fixed.sum():+,.0f} (at ₹2L, {cmp_.net_pct.mean():+.3f}% per trade)")
""")

    md("""
## 3 · Every trade, month by month

For each trade: the **decision card** (the stock, the strategy that drove it and why, the signal bar, the last bar
the decision used, entry price vs the strategy's level, stop, target, which strategies voted, the higher-ranked
stocks skipped at that scan and why, the exit and the P&L), then two charts:
* **left — what the system knew at the entry**: only the bars up to the decision; yellow = the signal bar; blue dashed =
  the strategy's level; black triangle = the entry (close of the confirming bar); red / green = stop / target.
* **right — what happened after**: the trailing stop as it moved up, the exit (X); grey bars after the exit are shown for
  context only and were never used.
""")
    for mth in MONTHS[year]:
        md(f"### {NAMES[int(mth[5:])]} {year}")
        code(f'tc.show_month(res, "{mth}")')

    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"]["kernelspec"] = {"name": "traiagent", "display_name": "TRAIAGENT (venv)", "language": "python"}
    out = ROOT / "notebooks" / f"{num}_causal_LONG_{year}.ipynb"
    out.write_text(nbf.writes(nb), encoding="utf-8")
    return out


if __name__ == "__main__":
    for y in (2025, 2026):
        print("wrote", build(y))

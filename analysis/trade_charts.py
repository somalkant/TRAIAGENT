"""
Per-trade cards and charts for the causal LONG notebooks (06 = 2025, 07 = 2026).

The LEFT panel shows only the bars that existed when the decision was taken (09:15 .. the bar that
confirmed the signal) — exactly what the system knew. The RIGHT panel shows what happened after the
entry; bars after the exit are greyed out and were never used for any decision.
"""
from __future__ import annotations

from datetime import date

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

from backtester.causal_engine import Store, costs

UP, DOWN, GREY = "#2e7d32", "#c62828", "#b0b0b0"


def day_bars(symbol: str, d: date) -> pd.DataFrame:
    s = Store([d], [symbol])
    today, _ = s.split(s.data.get(symbol), d)
    if len(today):
        today["hm"] = today.datetime.dt.strftime("%H:%M")
    return today


def _candles(ax, bars: pd.DataFrame, x0: int = 0, faded: bool = False) -> None:
    for i, b in enumerate(bars.itertuples()):
        x = x0 + i
        col = GREY if faded else (UP if b.close >= b.open else DOWN)
        ax.plot([x, x], [b.low, b.high], color=col, lw=0.8, zorder=2)
        lo, hi = sorted((b.open, b.close))
        ax.add_patch(Rectangle((x - 0.32, lo), 0.64, max(hi - lo, 1e-9), color=col, zorder=3,
                               alpha=0.45 if faded else 0.95))


def _xticks(ax, labels: list[str], every: int = 6) -> None:
    idx = list(range(0, len(labels), every))
    ax.set_xticks(idx)
    ax.set_xticklabels([labels[i] for i in idx], fontsize=7)


def card(t: dict) -> str:
    rr = (t["target0"] - t["entry"]) / (t["entry"] - t["stop0"]) if t["entry"] > t["stop0"] else float("nan")
    skipped = "; ".join(f"{s['symbol']} ({s['gate']})" for s in t.get("skipped_before", [])[:4]) or "none"
    net_pct = t["pnl_rs"] / (t["entry"] * t["qty"]) * 100 if t.get("qty") else float("nan")
    return (
        f"{t['date']}  {t['symbol']}   driver {t['driver']} — {t['reason']}\n"
        f"  signal bar {t['signal_time']} | decided on bars up to {t['decision_bar']} | ENTRY {t['entry_time']} @ {t['entry']:.2f}"
        f"  (strategy level {t['level']:.2f}, entry {t['drift_pct']:+.2f}% vs level)\n"
        f"  stop {t['stop']:.2f} ({(t['stop'] / t['entry'] - 1) * 100:+.2f}%)   target {t['target0']:.2f} "
        f"({(t['target0'] / t['entry'] - 1) * 100:+.2f}%)   RR {rr:.2f}   rank {t['rank']}\n"
        f"  votes: {t['agreeing']} agreeing, score {t['score']}, predicted win {t['pred']}% — {', '.join(t['strategies_fired'])}\n"
        f"  higher-ranked stocks skipped at this scan: {skipped}\n"
        f"  EXIT {t['exit_time']} @ {t['exit']:.2f} ({t['exit_reason']})   move {t['ret_pct']:+.2f}%   "
        f"P&L ₹{t['pnl_rs']:+,.0f} net ({net_pct:+.2f}%) on {t['qty']} shares"
    )


def plot_trade(t: dict, figsize=(14, 3.8), dpi=80):
    bars = day_bars(t["symbol"], date.fromisoformat(t["date"]))
    if bars.empty:
        print("  (no bars on file for this stock/day)")
        return None
    labels = bars.hm.tolist()
    k = labels.index(t["decision_bar"])                       # last bar the decision used
    x_exit = max(k + 1, next((i for i, lb in enumerate(labels) if lb >= t["exit_time"]), len(labels)) - 1)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=figsize, dpi=dpi, gridspec_kw={"width_ratios": [1, 1.5]})

    # LEFT — only what the system knew at the decision
    known = bars.iloc[:k + 1]
    _candles(a1, known)
    for y, c, ls, lab in ((t["level"], "#1565c0", "--", f"strategy level {t['level']:.2f}"),
                          (t["stop"], DOWN, "-", f"stop {t['stop']:.2f}"),
                          (t["target0"], UP, "-", f"target {t['target0']:.2f}")):
        a1.axhline(y, color=c, ls=ls, lw=1, label=lab)
    if t["signal_time"] in labels[:k + 1]:
        si = labels.index(t["signal_time"])
        a1.axvspan(si - 0.5, si + 0.5, color="#fff59d", alpha=0.6, zorder=1, label=f"signal bar {t['signal_time']}")
    a1.scatter([k], [t["entry"]], marker=">", s=90, color="black", zorder=5, label=f"entry {t['entry_time']} @ {t['entry']:.2f}")
    _xticks(a1, labels[:k + 1], every=max(1, (k + 1) // 6 or 1))
    a1.set_xlim(-1, k + 1.5)
    a1.set_title(f"{t['symbol']} {t['date']} — what the system knew at {t['entry_time']}", fontsize=9)
    a1.legend(fontsize=7, loc="best")

    # RIGHT — what happened after entry (post-exit bars greyed; never used)
    after = bars.iloc[k:]
    n_live = x_exit - k + 1
    _candles(a2, after.iloc[:n_live])
    _candles(a2, after.iloc[n_live:], x0=n_live, faded=True)
    a2.axhline(t["entry"], color="black", lw=0.8, ls=":", label=f"entry {t['entry']:.2f}")
    if t["target"] is not None:
        a2.axhline(t["target"], color=UP, lw=1, label=f"target {t['target']:.2f}")
    sp = t.get("stop_path") or [(t["entry_time"], t["stop"])]
    xs, ys = [], []
    for j, (when, lvl) in enumerate(sp):
        xi = max(0, next((i for i, lb in enumerate(labels) if lb >= when), len(labels)) - 1 - k)
        xs.append(xi); ys.append(lvl)
    xs.append(n_live - 1); ys.append(ys[-1])
    a2.step(xs, ys, where="post", color=DOWN, lw=1.2, label="stop (trailing)")
    a2.scatter([n_live - 1], [t["exit"]], marker="X", s=90, color="black", zorder=5,
               label=f"exit {t['exit_time']} @ {t['exit']:.2f} {t['exit_reason']}")
    _xticks(a2, after.hm.tolist(), every=6)
    a2.set_xlim(-1, len(after))
    colour = UP if t["pnl_rs"] > 0 else DOWN
    a2.set_title(f"after entry — {t['exit_reason']}   P&L ₹{t['pnl_rs']:+,.0f} ({t['ret_pct']:+.2f}% move)",
                 fontsize=9, color=colour)
    a2.legend(fontsize=7, loc="best")
    fig.tight_layout()
    plt.show()
    plt.close(fig)
    return fig


def show_month(results: list[dict], month: str) -> None:
    trades = [r["trade"] for r in results if r["date"].startswith(month) and r.get("trade")]
    days = [r for r in results if r["date"].startswith(month)]
    if not days:
        print("no trading days"); return
    net = sum(t["pnl_rs"] for t in trades)
    wins = sum(t["pnl_rs"] > 0 for t in trades)
    print(f"{month}: {len(days)} trading days, {len(trades)} trades, {wins} winners, net ₹{net:+,.0f}")
    no_trade = [r["date"] for r in days if not r.get("trade")]
    if no_trade:
        print(f"  no trade on: {', '.join(no_trade)}")
    for t in trades:
        print("\n" + card(t))
        plot_trade(t)


def month_table(results: list[dict]) -> pd.DataFrame:
    T = pd.DataFrame([r["trade"] for r in results if r.get("trade")])
    if T.empty:
        return T
    T["month"] = T.date.str[:7]
    T["net_pct"] = T.pnl_rs / (T.entry * T.qty) * 100
    g = T.groupby("month").agg(trades=("pnl_rs", "size"), win_pct=("pnl_rs", lambda x: round(100 * (x > 0).mean(), 1)),
                               net_rs=("pnl_rs", lambda x: round(x.sum())), avg_net_pct=("net_pct", lambda x: round(x.mean(), 3)))
    days = pd.Series([r["date"][:7] for r in results]).value_counts().rename("trading_days")
    return g.join(days)

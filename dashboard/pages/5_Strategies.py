"""
Page 5 — Strategy Performance
Leaderboard table, weight vs WR bubble chart, rolling performance lines,
strategy × year win-rate heatmap.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.data_loader import (
    load_paper_trades, apply_sidebar_filters,
    load_strategy_weights, load_lifetime_winrates, load_strategy_performance,
    explode_strategies,
)
from dashboard.charts import (
    weight_vs_wr_bubble, rolling_performance_lines, strategy_year_heatmap,
)
from dashboard.utils import winrate_cell_color

st.set_page_config(page_title="Strategies — Trading Agent", layout="wide")
st.title("Strategy Performance")

# ── Load data ─────────────────────────────────────────────────────────────────
weights     = load_strategy_weights()
lifetime_wr = load_lifetime_winrates()
perf        = load_strategy_performance()

df_all = load_paper_trades()
df = apply_sidebar_filters(
    df_all,
    st.session_state.get("symbol", "ALL"),
    st.session_state.get("years", []),
    st.session_state.get("phase", "All years"),
) if not df_all.empty else pd.DataFrame()

# ── Signal counts from paper_trades ──────────────────────────────────────────
signal_counts: dict = {}
if not df.empty:
    exploded = explode_strategies(df)
    if not exploded.empty:
        signal_counts = exploded["strategy"].value_counts().to_dict()

# ── Per-strategy P&L from paper_trades (driver_strategy basis) ───────────────
strat_pnl: dict = {}
if not df.empty and "driver_strategy" in df.columns:
    strat_pnl = df.groupby("driver_strategy")["pnl_rs"].sum().to_dict()

# ── Rolling win rates from perf arrays ───────────────────────────────────────
rolling_wr: dict = {}
for strat, arr in perf.items():
    if arr:
        s = pd.Series(arr, dtype=float)
        rolling_wr[strat] = s.rolling(50, min_periods=10).mean().iloc[-1] * 100 \
            if len(arr) >= 10 else (s.mean() * 100)

# ── Leaderboard table ─────────────────────────────────────────────────────────
st.subheader("Strategy Leaderboard")

all_strategies = sorted(set(weights) | set(lifetime_wr))
rows = []
for s in all_strategies:
    lwr = lifetime_wr.get(s, 50.0)
    rwr = rolling_wr.get(s, float("nan"))
    rows.append({
        "Strategy":     s,
        "Weight":       weights.get(s, 1.0),
        "Lifetime WR":  lwr,
        "Rolling WR":   rwr,
        "Signals":      signal_counts.get(s, 0),
        "P&L Rs":       strat_pnl.get(s, 0.0),
    })

leader = pd.DataFrame(rows).sort_values("Weight", ascending=False)

def _color_wr(val):
    try:
        color = winrate_cell_color(float(val))
        return f"color: {color}; font-weight: bold"
    except (TypeError, ValueError):
        return ""

styled_leader = (
    leader.style
    .applymap(_color_wr, subset=["Lifetime WR", "Rolling WR"])
    .format({
        "Weight":      "{:.4f}",
        "Lifetime WR": "{:.1f}%",
        "Rolling WR":  "{:.1f}%",
        "P&L Rs":      "Rs {:+,.0f}",
    }, na_rep="—")
)

st.dataframe(styled_leader, use_container_width=True, hide_index=True, height=350)

st.divider()

# ── Bubble + Rolling lines ────────────────────────────────────────────────────
col_bubble, col_rolling = st.columns(2)
with col_bubble:
    st.subheader("Weight vs Lifetime Win Rate")
    st.plotly_chart(
        weight_vs_wr_bubble(weights, lifetime_wr, signal_counts),
        use_container_width=True,
    )

with col_rolling:
    st.subheader("Rolling-10 Signal Win Rate")
    selected = st.multiselect(
        "Strategies to plot",
        options=sorted(perf.keys()),
        default=sorted(perf.keys())[:8],
    )
    st.plotly_chart(
        rolling_performance_lines(perf, selected or None),
        use_container_width=True,
    )

st.divider()

# ── Strategy × Year heatmap ───────────────────────────────────────────────────
st.subheader("Strategy × Year Win Rate Heatmap")
if df.empty:
    st.info("No trade data available for heatmap.")
else:
    st.plotly_chart(strategy_year_heatmap(df), use_container_width=True)

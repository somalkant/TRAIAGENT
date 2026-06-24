"""
Page 1 — Portfolio Overview
KPI metrics, cumulative P&L, win/loss donut, exit reason bar, conviction tier bar.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import CAPITAL, DAILY_LOSS_LIMIT
from dashboard.data_loader import load_paper_trades, apply_sidebar_filters
from dashboard.charts import (
    cumulative_pnl_chart, result_donut, exit_reason_bar, conviction_tier_bar,
)
from dashboard.utils import fmt_rs, fmt_pct

st.set_page_config(page_title="Portfolio — Trading Agent", layout="wide")
st.title("Portfolio Overview")

df_all = load_paper_trades()
if df_all.empty:
    st.warning("No trade data found. Run backtester or live agent first.")
    st.stop()

df = apply_sidebar_filters(
    df_all,
    st.session_state.get("symbol", "ALL"),
    st.session_state.get("years", []),
    st.session_state.get("phase", "All years"),
)

if df.empty:
    st.info("No trades match the current sidebar filters.")
    st.stop()

# ── KPI row ───────────────────────────────────────────────────────────────────
total_trades   = len(df)
total_pnl      = df["pnl_rs"].sum()
win_mask       = df["result"].isin(["EXACT_WIN", "WIN"])
win_rate       = win_mask.mean() * 100
exact_wins     = (df["result"] == "EXACT_WIN").sum()
wins           = (df["result"] == "WIN").sum()
losses         = (df["result"] == "LOSS").sum()

gross_profit = df.loc[win_mask, "pnl_rs"].sum()
gross_loss   = df.loc[~win_mask, "pnl_rs"].sum()
profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else float("inf")
avg_win      = df.loc[win_mask, "pnl_rs"].mean() if win_mask.any() else 0
avg_loss     = df.loc[~win_mask, "pnl_rs"].mean() if (~win_mask).any() else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total P&L", fmt_rs(total_pnl))
c2.metric("Win Rate", fmt_pct(win_rate))
c3.metric("Total Trades", total_trades)
c4.metric("Profit Factor", f"{profit_factor:.2f}")
c5.metric("Avg Win", fmt_rs(avg_win))
c6.metric("Avg Loss", fmt_rs(avg_loss))

st.divider()

# ── Cumulative P&L chart ──────────────────────────────────────────────────────
st.plotly_chart(cumulative_pnl_chart(df, DAILY_LOSS_LIMIT), use_container_width=True)

st.divider()

# ── Bottom row: 3 charts ──────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    st.plotly_chart(result_donut(df), use_container_width=True)
with col2:
    st.plotly_chart(exit_reason_bar(df), use_container_width=True)
with col3:
    st.plotly_chart(conviction_tier_bar(df), use_container_width=True)

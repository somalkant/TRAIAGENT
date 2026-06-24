"""
Page 2 — Signals & Live Monitor
Open trade card, today's signals, strategy firing frequency, score histogram, heatmap.
Auto-refresh toggle (30s) for live session monitoring.
"""

import sys
import time
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.data_loader import (
    load_paper_trades, apply_sidebar_filters,
    load_live_open_trade, load_live_trades,
)
from dashboard.charts import (
    strategy_firing_freq, composite_score_histogram, strategy_month_heatmap,
)
from dashboard.utils import fmt_rs

st.set_page_config(page_title="Signals — Trading Agent", layout="wide")
st.title("Signals & Live Monitor")

# ── Auto-refresh toggle ───────────────────────────────────────────────────────
col_hdr, col_toggle = st.columns([4, 1])
with col_hdr:
    st.caption(f"Today: {date.today()}")
with col_toggle:
    auto_refresh = st.toggle("Auto-refresh (30s)", value=False)

# ── Open trade card ───────────────────────────────────────────────────────────
open_trade = load_live_open_trade()
live_trades = load_live_trades()

col_card, col_signals = st.columns([1, 2])

with col_card:
    st.subheader("Open Trade")
    if open_trade:
        st.success(f"**{open_trade.get('symbol', '—')}**")
        for k, v in open_trade.items():
            if k != "symbol":
                label = k.replace("_", " ").title()
                if "pnl" in k.lower() or "price" in k.lower() or "rs" in k.lower():
                    try:
                        st.metric(label, fmt_rs(float(v)))
                    except (TypeError, ValueError):
                        st.write(f"**{label}:** {v}")
                else:
                    st.write(f"**{label}:** {v}")
    else:
        st.info("No open trade (live_open_trade.json not found or empty).")

with col_signals:
    st.subheader("Today's Signals")
    if not live_trades.empty:
        today_str = str(date.today())
        today_df = live_trades[live_trades["date"].astype(str).str.startswith(today_str)]
        if today_df.empty:
            st.info("No signals fired today yet.")
        else:
            display_cols = [c for c in ["signal_time", "symbol", "strategies_fired",
                                        "composite_score", "result", "pnl_rs"]
                            if c in today_df.columns]
            st.dataframe(today_df[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No live session data (live_paper_trades.csv not found).")

st.divider()

# ── Historical signals from paper_trades ──────────────────────────────────────
df_all = load_paper_trades()
if df_all.empty:
    st.warning("No paper_trades.csv found.")
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

st.subheader("Strategy Firing Frequency")
st.plotly_chart(strategy_firing_freq(df), use_container_width=True)

st.divider()

col_hist, col_heat = st.columns(2)
with col_hist:
    st.subheader("Composite Score Histogram")
    st.plotly_chart(composite_score_histogram(df), use_container_width=True)
with col_heat:
    st.subheader("Strategy × Month Win Rate")
    if "month" not in df.columns:
        df["month"] = df["date"].dt.to_period("M").astype(str)
    st.plotly_chart(strategy_month_heatmap(df), use_container_width=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(30)
    st.rerun()

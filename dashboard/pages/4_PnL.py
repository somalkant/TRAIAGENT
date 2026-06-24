"""
Page 4 — P&L Analysis
Daily / Monthly / Yearly view toggle, drawdown chart, yearly summary table.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import CAPITAL, DAILY_LOSS_LIMIT
from dashboard.data_loader import (
    load_paper_trades, apply_sidebar_filters, load_historical_parquets,
)
from dashboard.charts import (
    daily_pnl_bar, monthly_pnl_bar, drawdown_chart, yearly_summary_table,
)
from dashboard.utils import fmt_rs

st.set_page_config(page_title="P&L — Trading Agent", layout="wide")
st.title("P&L Analysis")

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

# ── Period toggle ─────────────────────────────────────────────────────────────
period = st.radio("View", ["Monthly", "Daily", "Yearly"], horizontal=True)

if period == "Daily":
    st.plotly_chart(daily_pnl_bar(df), use_container_width=True)

elif period == "Monthly":
    if "month" not in df.columns:
        df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly_target = CAPITAL * 0.03
    st.plotly_chart(monthly_pnl_bar(df, monthly_target), use_container_width=True)

else:  # Yearly
    parquet_df = load_historical_parquets()
    st.plotly_chart(yearly_summary_table(df, parquet_df), use_container_width=True)

st.divider()

# ── Drawdown chart (always shown) ─────────────────────────────────────────────
st.subheader("Equity Curve & Drawdown")
st.plotly_chart(drawdown_chart(df, CAPITAL, DAILY_LOSS_LIMIT), use_container_width=True)

st.divider()

# ── Yearly summary table (always shown) ───────────────────────────────────────
st.subheader("Yearly Summary")
parquet_df = load_historical_parquets()
if not parquet_df.empty or not df.empty:
    import pandas as pd
    frames = []
    if not df.empty:
        frames.append(df)
    grp_data = pd.concat(frames, ignore_index=True) if frames else df

    if not grp_data.empty and "year" in grp_data.columns:
        grp = grp_data.groupby("year")
        rows = []
        for year, g in grp:
            total  = len(g)
            wins   = g["result"].isin(["EXACT_WIN", "WIN"]).sum() if "result" in g.columns else 0
            wr     = wins / total * 100 if total else 0
            pnl    = g["pnl_rs"].sum()
            pnl_pct = pnl / CAPITAL * 100
            rows.append({
                "Year": int(year),
                "Trades": total,
                "Win %": f"{wr:.1f}%",
                "P&L Rs": fmt_rs(pnl),
                "P&L %": f"{pnl_pct:.1f}%",
            })
        summary = pd.DataFrame(rows).sort_values("Year")
        st.dataframe(summary, use_container_width=True, hide_index=True)

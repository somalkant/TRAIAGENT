"""
Page 3 — Trade History
Sortable, filterable table with row coloring by result. Download CSV button.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.data_loader import load_paper_trades, apply_sidebar_filters
from dashboard.utils import RESULT_COLORS

st.set_page_config(page_title="Trades — Trading Agent", layout="wide")
st.title("Trade History")

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

# ── Page-level filters ────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    sym_opts = ["ALL"] + sorted(df["symbol"].unique().tolist())
    sym_filter = st.selectbox("Symbol", sym_opts)
with col2:
    year_opts = ["ALL"] + sorted(df["year"].unique().tolist())
    year_filter = st.selectbox("Year", year_opts)
with col3:
    result_opts = ["ALL"] + sorted(df["result"].unique().tolist())
    result_filter = st.selectbox("Result", result_opts)
with col4:
    driver_opts = ["ALL"] + sorted(df["driver_strategy"].unique().tolist())
    driver_filter = st.selectbox("Driver Strategy", driver_opts)

mask = pd.Series(True, index=df.index)
if sym_filter != "ALL":
    mask &= df["symbol"] == sym_filter
if year_filter != "ALL":
    mask &= df["year"] == int(year_filter)
if result_filter != "ALL":
    mask &= df["result"] == result_filter
if driver_filter != "ALL":
    mask &= df["driver_strategy"] == driver_filter

filtered = df[mask].copy()

# ── Display columns ───────────────────────────────────────────────────────────
display_cols = [c for c in [
    "date", "symbol", "entry_price", "exit_price",
    "pnl_rs", "pnl_pct", "result", "driver_strategy",
    "agreeing_count", "composite_score", "rr",
    "conviction_tier", "exit_reason",
] if c in filtered.columns]

st.caption(f"Showing {len(filtered):,} of {len(df):,} trades")

# Row styling via Pandas Styler
def _row_color(row):
    color_map = {"EXACT_WIN": "#16a34a22", "WIN": "#86efac22", "LOSS": "#f8717122"}
    bg = color_map.get(row["result"], "")
    return [f"background-color: {bg}" if bg else ""] * len(row)

styled = (
    filtered[display_cols]
    .sort_values("date", ascending=False)
    .style.apply(_row_color, axis=1)
    .format({
        "pnl_rs": "Rs {:+,.0f}",
        "pnl_pct": "{:.2f}%",
        "composite_score": "{:.4f}",
        "entry_price": "{:.2f}",
        "exit_price": "{:.2f}",
        "rr": "{:.1f}",
    }, na_rep="—")
)

st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

# ── Download ──────────────────────────────────────────────────────────────────
csv_bytes = filtered[display_cols].to_csv(index=False).encode()
st.download_button(
    label="Download CSV",
    data=csv_bytes,
    file_name="trades_filtered.csv",
    mime="text/csv",
)

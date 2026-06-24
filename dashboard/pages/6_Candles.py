"""
Page 6 — Candle Chart
5-min OHLCV candlestick for any symbol + date in the parquet archive.
Overlays entry/exit markers and stop/target lines if a trade exists for that day.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.data_loader import (
    load_candles, load_paper_trades,
    available_symbols_for_year, available_years,
)
from dashboard.charts import candle_chart
from dashboard.utils import fmt_rs

st.set_page_config(page_title="Candles — Trading Agent", layout="wide")
st.title("5-Min Candle Chart")
st.caption("Shows downloaded parquet data. Today's candles appear after next morning's data pull.")

# ── Controls ──────────────────────────────────────────────────────────────────
years = available_years()
if not years:
    st.error("No stock parquet data found in data/stocks/.")
    st.stop()

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    selected_year = st.selectbox("Year", options=list(reversed(years)), index=0)

with col2:
    symbols = available_symbols_for_year(selected_year)
    if not symbols:
        st.warning(f"No parquet files found for {selected_year}.")
        st.stop()

    # Pre-select the sidebar symbol if it's available for this year
    sidebar_sym = st.session_state.get("symbol", "ALL")
    default_sym = sidebar_sym if sidebar_sym in symbols else symbols[0]
    selected_symbol = st.selectbox("Symbol", options=symbols,
                                   index=symbols.index(default_sym))

with col3:
    selected_date = st.date_input(
        "Date",
        value=date(selected_year, 6, 1),
        min_value=date(selected_year, 1, 1),
        max_value=date(selected_year, 12, 31),
    )

# ── Load candles ──────────────────────────────────────────────────────────────
with st.spinner(f"Loading {selected_symbol} {selected_year}..."):
    candles = load_candles(selected_symbol, selected_year)

if candles.empty:
    st.warning(f"No data for {selected_symbol} in {selected_year}.")
    st.stop()

date_str = str(selected_date)

# Check if the selected date has candle data
available_dates = sorted(candles["datetime"].dt.date.unique())
available_date_strs = [str(d) for d in available_dates]

if date_str not in available_date_strs:
    # Find nearest trading day with data
    nearest = min(available_date_strs, key=lambda d: abs(
        (date.fromisoformat(d) - selected_date).days
    ))
    st.info(f"No candles for {date_str} (weekend/holiday?). Showing nearest trading day: {nearest}")
    date_str = nearest

# ── Find matching trade ───────────────────────────────────────────────────────
trade_row = None
df_trades = load_paper_trades()
if not df_trades.empty:
    match = df_trades[
        (df_trades["symbol"] == selected_symbol) &
        (df_trades["date"].astype(str) == date_str)
    ]
    if not match.empty:
        trade_row = match.iloc[0]

# ── Chart ─────────────────────────────────────────────────────────────────────
st.plotly_chart(
    candle_chart(candles, trade_row=trade_row, date_str=date_str),
    use_container_width=True,
)

# ── Trade details card (if trade exists) ─────────────────────────────────────
if trade_row is not None:
    st.divider()
    st.subheader("Trade on this day")

    result = trade_row.get("result", "")
    color  = {"EXACT_WIN": "success", "WIN": "success", "LOSS": "error"}.get(result, "info")
    getattr(st, color)(f"**{result}**  —  {fmt_rs(trade_row.get('pnl_rs', 0))}  ({trade_row.get('pnl_pct', 0):.2f}%)")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Entry", f"{trade_row.get('entry_price', 0):.2f}")
    c2.metric("Exit",  f"{trade_row.get('exit_price', 0):.2f}")
    c3.metric("Stop",  f"{trade_row.get('stop_loss', 0):.2f}")
    c4.metric("Target",f"{trade_row.get('target', 0):.2f}")
    c5.metric("RR",    f"{trade_row.get('rr', 0):.1f}")

    st.write(f"**Driver:** {trade_row.get('driver_strategy', '—')}  |  "
             f"**Exit reason:** {trade_row.get('exit_reason', '—')}  |  "
             f"**Conviction:** {trade_row.get('conviction_tier', '—')}  |  "
             f"**Score:** {trade_row.get('composite_score', 0):.4f}")
    st.write(f"**Strategies fired:** {trade_row.get('strategies_fired', '—')}")
    st.write(f"**Reason:** {trade_row.get('reason', '—')}")

else:
    st.info(f"No trade in paper_trades.csv for {selected_symbol} on {date_str}.")

# ── Date navigator ────────────────────────────────────────────────────────────
st.divider()
st.caption(f"Available trading days in {selected_year}: {len(available_dates)}  |  "
           f"Showing: {date_str}")

# Quick-jump: show all dates with trades for this symbol
if not df_trades.empty:
    sym_trades = df_trades[df_trades["symbol"] == selected_symbol].sort_values("date", ascending=False)
    if not sym_trades.empty:
        with st.expander(f"All {selected_symbol} trades ({len(sym_trades)})"):
            show_cols = [c for c in ["date", "result", "pnl_rs", "driver_strategy",
                                      "entry_price", "exit_price", "exit_reason"]
                         if c in sym_trades.columns]
            st.dataframe(sym_trades[show_cols], use_container_width=True, hide_index=True)

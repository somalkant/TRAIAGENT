"""
Phase 2.6 — Trading Agent Monitoring Dashboard
Entry point: sidebar filters + portfolio overview redirect to multi-page nav.

Run:
    .\\venv\\Scripts\\streamlit.exe run dashboard\\app.py --server.port 8501
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    CAPITAL, DAILY_LOSS_LIMIT,
    TESTING_START_YEAR, TESTING_END_YEAR, LEARNING_END_YEAR,
)
from dashboard.data_loader import load_paper_trades

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Agent Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar — global filters (persisted in session_state) ────────────────────
with st.sidebar:
    st.title("Trading Agent")
    st.caption("Phase 2.6 — Monitoring Dashboard")
    st.divider()

    df_all = load_paper_trades()
    symbols = ["ALL"] + sorted(df_all["symbol"].unique().tolist()) if not df_all.empty else ["ALL"]

    if "symbol" not in st.session_state:
        st.session_state["symbol"] = "ALL"
    if "years" not in st.session_state:
        st.session_state["years"] = list(range(TESTING_START_YEAR, TESTING_END_YEAR + 1))
    if "phase" not in st.session_state:
        st.session_state["phase"] = "Testing only"

    st.session_state["symbol"] = st.selectbox(
        "Symbol", symbols, index=symbols.index(st.session_state["symbol"])
        if st.session_state["symbol"] in symbols else 0,
    )

    all_years = list(range(2017, TESTING_END_YEAR + 1))
    st.session_state["years"] = st.multiselect(
        "Years", all_years, default=st.session_state["years"],
    )

    st.session_state["phase"] = st.radio(
        "Phase",
        ["Testing only", "Learning only", "All years"],
        index=["Testing only", "Learning only", "All years"].index(st.session_state["phase"]),
    )

    st.divider()
    st.caption(f"Capital: Rs {CAPITAL:,.0f}")
    st.caption(f"Daily loss limit: Rs {DAILY_LOSS_LIMIT:,.0f}")

# ── Home page content ─────────────────────────────────────────────────────────
st.title("Trading Agent — Monitoring Dashboard")
st.markdown(
    "Use the **sidebar** to filter by symbol, year, and phase.  \n"
    "Navigate pages using the left panel."
)

if df_all.empty:
    st.warning("No paper_trades.csv found at `data/trade_logs/paper_trades.csv`. "
               "Run the backtester or live agent first.")
else:
    from dashboard.data_loader import apply_sidebar_filters
    df = apply_sidebar_filters(
        df_all,
        st.session_state["symbol"],
        st.session_state["years"],
        st.session_state["phase"],
    )
    total_trades = len(df)
    total_pnl    = df["pnl_rs"].sum() if total_trades else 0
    win_rate     = df["result"].isin(["EXACT_WIN", "WIN"]).mean() * 100 if total_trades else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Trades", total_trades)
    c2.metric("Total P&L", f"Rs {total_pnl:+,.0f}")
    c3.metric("Win Rate", f"{win_rate:.1f}%")

    st.info("Select a page from the left sidebar to explore detailed analytics.")

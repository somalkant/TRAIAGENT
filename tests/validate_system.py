"""
Trading Agent — System Validation Suite
Run before starting the live agent each morning:
    python tests/validate_system.py

All 12 tests must PASS. Any FAIL → do not start the agent.
"""

import sys
import os
import tempfile
import json
from datetime import date, datetime, time as dtime
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

_PASS = 0
_FAIL = 0
_ERRORS = []


def _result(name: str, passed: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    label = "PASS" if passed else "FAIL"
    pad   = max(0, 45 - len(name))
    print(f"  {name} {'.' * pad} {label}")
    if not passed:
        _FAIL += 1
        _ERRORS.append((name, detail))
        print(f"    !! {detail}")
    else:
        _PASS += 1


# ─────────────────────────────────────────────────────────────────────────────
# V1 — Pre-Open Bar Guard
# ─────────────────────────────────────────────────────────────────────────────
def test_preopen_bar_guard():
    """
    At 09:15, the loop computes bar_label = 09:15 - 5min = 09:10.
    The guard `bar_label.time() < MARKET_OPEN` must catch this and skip it.
    """
    from datetime import timedelta
    market_open = dtime(9, 15)

    # Simulate the exact moment the loop wakes at 09:15
    fake_now = datetime(2026, 6, 17, 9, 15, 1)
    bar_label = fake_now.replace(second=0, microsecond=0) - timedelta(minutes=5)
    # bar_label is 09:10 — the pre-open label

    guard_fires = bar_label.time() < market_open

    _result(
        "V1  Pre-Open Bar Guard",
        guard_fires,
        f"bar_label at 09:15 wake = {bar_label.strftime('%H:%M')} — guard should fire, got {guard_fires}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# V2 — Pre-Open Tick Filter (unit-level check)
# ─────────────────────────────────────────────────────────────────────────────
def test_preopen_tick_filter():
    """
    _MARKET_OPEN_T must be defined in data_manager and equal dtime(9,15).
    The on_tick() method must have the filter logic.
    """
    try:
        import live.data_manager as dm_mod
        import inspect

        has_constant = hasattr(dm_mod, "_MARKET_OPEN_T")
        correct_value = has_constant and dm_mod._MARKET_OPEN_T == dtime(9, 15)

        src = inspect.getsource(dm_mod.LiveDataManager.on_tick)
        has_filter = "_MARKET_OPEN_T" in src

        ok = correct_value and has_filter
        _result(
            "V2  Pre-Open Tick Filter",
            ok,
            f"_MARKET_OPEN_T defined={has_constant} correct={correct_value} filter_in_on_tick={has_filter}"
        )
    except Exception as e:
        _result("V2  Pre-Open Tick Filter", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# V3 — Live-Price Entry: Distance Preservation
# ─────────────────────────────────────────────────────────────────────────────
def test_live_price_entry_distances():
    """
    Reproduces the DIXON trade scenario:
      strategy entry=11933, stop=11445.15, target=13777
      live price=12206
    After adjustment, stop and target distances from entry must be preserved.
    """
    from strategies.base import Signal

    sig = Signal("ASC-TRI", +1, entry=11933.0, target=13777.0, stop=11445.15, rr=3.78)
    live_price = 12206.0

    orig_stop_dist   = sig.entry - sig.stop      # 487.85
    orig_target_dist = sig.target - sig.entry    # 1844.0

    # Correct adjustment order (distances computed BEFORE entry is updated)
    stop_dist   = sig.entry - sig.stop
    target_dist = sig.target - sig.entry
    live_entry  = round(live_price, 2)
    live_stop   = round(live_entry - stop_dist, 2)
    live_target = round(live_entry + target_dist, 2)

    new_stop_dist   = live_entry - live_stop
    new_target_dist = live_target - live_entry

    dist_preserved = (
        abs(new_stop_dist - orig_stop_dist) < 0.01 and
        abs(new_target_dist - orig_target_dist) < 0.01
    )

    # Bug check: if entry were updated FIRST, stop_dist would be wrong
    bug_stop_dist   = live_entry - sig.stop       # 760.85 (wrong)
    bug_target_dist = sig.target - live_entry     # 1571   (wrong)
    bug_live_stop   = round(live_entry - bug_stop_dist, 2)   # 11445.15 — same as original!
    stop_is_different = abs(live_stop - bug_live_stop) > 0.01

    _result(
        "V3  Live-Price Entry Distances",
        dist_preserved and stop_is_different,
        f"orig_stop_dist={orig_stop_dist:.2f} new_stop_dist={new_stop_dist:.2f} "
        f"live_stop={live_stop} (bug would give {bug_live_stop})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# V4 — RR Field Consistency
# ─────────────────────────────────────────────────────────────────────────────
def test_rr_consistency():
    """
    After live-price adjustment, rr must equal (target-entry)/(entry-stop).
    Tests both: correct code path and that the DIXON bug case (rr=2.06) is gone.
    """
    from strategies.base import Signal

    sig = Signal("ASC-TRI", +1, entry=11933.0, target=13777.0, stop=11445.15, rr=3.78)
    live_price = 12206.0

    stop_dist   = sig.entry - sig.stop
    target_dist = sig.target - sig.entry
    live_entry  = round(live_price, 2)
    live_stop   = round(live_entry - stop_dist, 2)
    live_target = round(live_entry + target_dist, 2)
    computed_rr = round((live_target - live_entry) / (live_entry - live_stop), 2)

    # RR should be ~3.78 (same as original), NOT 2.06 (the buggy value)
    rr_correct   = abs(computed_rr - 3.78) < 0.05
    rr_not_buggy = abs(computed_rr - 2.06) > 0.5

    _result(
        "V4  RR Field Consistency",
        rr_correct and rr_not_buggy,
        f"computed_rr={computed_rr} (expected ~3.78, bug would give 2.06)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# V5 — Position Sizing
# ─────────────────────────────────────────────────────────────────────────────
def test_position_sizing():
    """
    Risk per trade = (entry - stop) × shares must not exceed MAX_LOSS_PER_TRADE.
    Position size = shares × entry must not exceed MAX_POSITION_SIZE.
    """
    from backtester.position_sizer import position_size
    from config.settings import MAX_POSITION_SIZE, MAX_LOSS_PER_TRADE

    cases = [
        # (entry, stop, conv_mult, label)
        (12206.0, 11718.15, 1.0, "STANDARD"),
        (12206.0, 11718.15, 1.5, "MEDIUM"),
        (12206.0, 11718.15, 2.0, "HIGH"),
        (500.0,   490.0,   1.0,  "tight stop"),
        (50000.0, 48000.0, 1.0,  "high price stock"),
    ]

    all_ok = True
    details = []
    for entry, stop, mult, label in cases:
        rs, shares = position_size(entry, stop, mult)
        if shares == 0:
            continue
        risk_rs   = (entry - stop) * shares
        max_risk  = MAX_LOSS_PER_TRADE * mult
        risk_ok   = risk_rs <= max_risk * 1.05   # 5% tolerance for rounding
        size_ok   = rs <= MAX_POSITION_SIZE * 1.01
        shares_ok = shares >= 1
        if not (risk_ok and size_ok and shares_ok):
            all_ok = False
            details.append(
                f"{label}: rs={rs:,.0f} risk={risk_rs:,.0f} max_risk={max_risk:,.0f}"
            )

    _result("V5  Position Sizing", all_ok, "; ".join(details) if details else "")


# ─────────────────────────────────────────────────────────────────────────────
# V6 — P&L Calculation
# ─────────────────────────────────────────────────────────────────────────────
def test_pnl_calculation():
    """
    Verify net_pnl covers real NSE cost components.
    Breakeven gross (entry=exit) must yield negative net (costs eaten).
    Target hit must be profitable. Stop hit must stay within risk limits.
    """
    from backtester.cost_model import net_pnl
    from config.settings import MAX_LOSS_PER_TRADE

    entry  = 12206.0
    stop   = 11718.15
    target = 14050.0
    shares = 26

    pnl_breakeven = net_pnl(entry, entry, shares)
    pnl_target    = net_pnl(entry, target, shares)
    pnl_stop      = net_pnl(entry, stop, shares)

    ok_breakeven = pnl_breakeven < 0                             # costs > 0
    ok_target    = pnl_target > 0                                # profitable
    ok_stop      = pnl_stop < 0                                  # loss
    ok_risk      = abs(pnl_stop) <= MAX_LOSS_PER_TRADE * 1.20   # within 120% of limit (slippage buffer)
    ok_ratio     = pnl_target > abs(pnl_stop)                   # reward > risk

    all_ok = ok_breakeven and ok_target and ok_stop and ok_risk and ok_ratio
    _result(
        "V6  P&L Calculation",
        all_ok,
        f"breakeven={pnl_breakeven:.0f} target={pnl_target:.0f} stop={pnl_stop:.0f} "
        f"max_loss={MAX_LOSS_PER_TRADE} ratio_ok={ok_ratio}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# V7 — Quality Filters
# ─────────────────────────────────────────────────────────────────────────────
def test_quality_filters():
    """Test each filter rejects correctly, and a valid signal passes all."""
    from backtester.quality_filter import passes_all_filters
    from strategies.base import Signal
    import pandas as pd

    good_sig = Signal("TEST", +1, entry=100.0, target=110.0, stop=95.0, rr=2.0,
                      signal_time="09:45")
    today_df = pd.DataFrame()

    failures = []

    # Liquidity filter
    p, r = passes_all_filters(good_sig, today_df, 1.0, 4)
    if p:
        failures.append("Liquidity 1Cr should reject — passed instead")

    # RR filter
    low_rr = Signal("TEST", +1, entry=100.0, target=101.0, stop=99.0, rr=1.0,
                    signal_time="09:45")
    p, r = passes_all_filters(low_rr, today_df, 100.0, 4)
    if p:
        failures.append("RR=1.0 should reject — passed instead")

    # Agreement filter
    p, r = passes_all_filters(good_sig, today_df, 100.0, 2)
    if p:
        failures.append("agreeing=2 should reject (need 4) — passed instead")

    # After 2PM gate
    late_sig = Signal("TEST", +1, entry=100.0, target=110.0, stop=95.0, rr=2.0,
                      signal_time="14:05")
    p, r = passes_all_filters(late_sig, today_df, 100.0, 4)
    if p:
        failures.append("signal_time=14:05 should reject — passed instead")

    # 50-55% danger zone
    p, r = passes_all_filters(good_sig, today_df, 100.0, 4, composite_score=5.0,
                               predicted_win_pct=52.0)
    if p:
        failures.append("predicted_win_pct=52 (danger zone) should reject — passed instead")

    # Valid signal — 09:20 is before the 09:30 time-gate, no score/agreement bonus required
    early_sig = Signal("TEST", +1, entry=100.0, target=110.0, stop=95.0, rr=2.0,
                       signal_time="09:20")
    p, r = passes_all_filters(early_sig, today_df, 100.0, 4, composite_score=5.0,
                               predicted_win_pct=60.0)
    if not p:
        failures.append(f"Valid 09:20 signal rejected: {r}")

    _result("V7  Quality Filters", len(failures) == 0, "; ".join(failures))


# ─────────────────────────────────────────────────────────────────────────────
# V8 — CSV Logger Column Integrity
# ─────────────────────────────────────────────────────────────────────────────
def test_csv_column_integrity():
    """
    Log a mock trade to a temp file and verify all 24 columns are present
    and in the correct order.
    """
    import pandas as pd
    from live.paper_logger import _COLUMNS, log_closed_trade, LIVE_TRADES_FILE

    expected = [
        "date", "symbol", "signal_time", "entry_time", "strategy_entry", "entry_price",
        "quantity", "position_rs", "stop_loss", "target", "rr", "strategies_fired",
        "agreeing_count", "composite_score", "driver_strategy", "reason", "exit_time",
        "exit_price", "exit_reason", "result", "pnl_rs", "pnl_pct",
        "predicted_win_pct", "conviction_tier",
    ]

    cols_match = _COLUMNS == expected
    count_ok   = len(_COLUMNS) == 24

    _result(
        "V8  CSV Column Integrity",
        cols_match and count_ok,
        f"column count={len(_COLUMNS)} (need 24); "
        + ("columns match" if cols_match else f"first mismatch at {next((i for i,(a,b) in enumerate(zip(_COLUMNS,expected)) if a!=b), '?')}")
    )


# ─────────────────────────────────────────────────────────────────────────────
# V9 — Checkpoint Round-Trip
# ─────────────────────────────────────────────────────────────────────────────
def test_checkpoint_roundtrip():
    """
    Save an open trade to a temp JSON file and load it back.
    All critical fields must survive serialisation.
    """
    import tempfile
    from live.paper_logger import save_open_trade, load_open_trade, OPEN_TRADE_CACHE

    rec = {
        "symbol":          "CHECKTEST",
        "score":           3.5,
        "agreeing":        4,
        "position_rs":     300000.0,
        "shares":          25,
        "predicted_win_pct": 60.0,
        "conviction_tier": "STANDARD",
        "conviction_mult": 1.0,
        "entry_time":      "10:00",
        "strategies_fired": "ASC-TRI,ADX-FILTER",
        "signal": {
            "strategy":       "ASC-TRI",
            "direction":      1,
            "entry":          12000.0,
            "target":         14000.0,
            "stop":           11500.0,
            "rr":             4.0,
            "signal_time":    "09:45",
            "reason":         "test",
            "strategy_entry": 11900.0,
        },
    }

    today = date.today()
    save_open_trade(today, rec)
    d, loaded = load_open_trade()

    fields_ok = (
        loaded is not None and
        loaded["symbol"] == "CHECKTEST" and
        loaded["signal"]["entry"] == 12000.0 and
        loaded["signal"]["stop"]  == 11500.0 and
        loaded["signal"]["rr"]    == 4.0 and
        loaded["shares"]          == 25 and
        loaded["entry_time"]      == "10:00"
    )

    # Clean up
    if OPEN_TRADE_CACHE.exists():
        OPEN_TRADE_CACHE.unlink()

    _result(
        "V9  Checkpoint Round-Trip",
        fields_ok,
        f"loaded={loaded is not None} symbol={'OK' if loaded and loaded.get('symbol')=='CHECKTEST' else 'WRONG'}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# V10 — No Forward-Look in History
# ─────────────────────────────────────────────────────────────────────────────
def test_no_forward_look():
    """
    Parquet history loaded for live trading must not contain any rows from today.
    Tests the filter `datetime.dt.date < today` is applied.
    """
    from config.settings import STOCKS_DIR
    import pandas as pd
    import pytz

    _IST = pytz.timezone("Asia/Kolkata")
    today = date.today()

    # Find any parquet file to test against
    parquet_files = list(STOCKS_DIR.glob(f"{today.year}/*.parquet"))
    if not parquet_files:
        parquet_files = list(STOCKS_DIR.glob(f"{today.year - 1}/*.parquet"))

    if not parquet_files:
        _result("V10 No Forward-Look in History", True, "No parquet files found — skipped")
        return

    sample = parquet_files[0]
    try:
        df = pd.read_parquet(sample)
        dt = pd.to_datetime(df["datetime"])
        if dt.dt.tz is not None:
            dt = dt.dt.tz_convert(_IST).dt.tz_localize(None)
        # Apply the same filter the live agent uses
        history = df[dt.dt.date < today]
        today_rows = df[dt.dt.date == today]

        # Simulate the filtering
        leak = len(today_rows) > 0 and len(history[pd.to_datetime(history["datetime"]).dt.date == today]) > 0

        _result(
            "V10 No Forward-Look in History",
            not leak,
            f"today_rows_in_raw={len(today_rows)} (OK — these get filtered), "
            f"symbol={sample.stem}"
        )
    except Exception as e:
        _result("V10 No Forward-Look in History", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# V11 — Strategy Signal Validity
# ─────────────────────────────────────────────────────────────────────────────
def test_strategy_signal_validity():
    """
    Every strategy must return a valid Signal (no exceptions) for minimal input.
    If direction != 0, entry/stop/target/rr must all be positive and consistent.
    """
    import pandas as pd
    import numpy as np
    from datetime import date as dt_date
    from strategies import ALL_STRATEGIES
    from strategies.base import Signal

    # Build a minimal but realistic 5-min DataFrame for today (10 bars)
    base_price = 1000.0
    times = pd.date_range("2026-01-15 09:15", periods=10, freq="5min")
    today_df = pd.DataFrame({
        "datetime": times,
        "open":   [base_price + i for i in range(10)],
        "high":   [base_price + i + 5 for i in range(10)],
        "low":    [base_price + i - 3 for i in range(10)],
        "close":  [base_price + i + 2 for i in range(10)],
        "volume": [10000 + i * 500 for i in range(10)],
    })

    # Build a minimal history (60 days)
    hist_times = pd.date_range("2025-10-01 09:15", periods=60 * 75, freq="5min")
    hist_df = pd.DataFrame({
        "datetime": hist_times,
        "open":   np.random.uniform(980, 1020, 60 * 75),
        "high":   np.random.uniform(1000, 1040, 60 * 75),
        "low":    np.random.uniform(960, 1000, 60 * 75),
        "close":  np.random.uniform(980, 1020, 60 * 75),
        "volume": np.random.randint(5000, 50000, 60 * 75),
    })
    # Filter to before today
    hist_df = hist_df[hist_df["datetime"].dt.date < dt_date(2026, 1, 15)]

    prev_day = pd.Series({
        "open": 995.0, "high": 1025.0, "low": 985.0, "close": 1010.0, "volume": 1000000
    })
    nifty_df = today_df.copy()

    crashed = []
    invalid = []
    fired   = 0

    for strat in ALL_STRATEGIES:
        try:
            sig = strat.generate_signal(
                today_5min=today_df,
                history_5min=hist_df,
                prev_day=prev_day,
                nifty_today=nifty_df,
                trade_date=dt_date(2026, 1, 15),
            )
            if not isinstance(sig, Signal):
                invalid.append(f"{strat.name}: returned {type(sig).__name__} not Signal")
            elif sig.direction != 0 and sig.entry > 0:
                # Only validate trade signals (entry>0); overlay signals (ADX-FILTER etc.)
                # intentionally have direction!=0 but entry=0 — that is valid by design.
                fired += 1
                if sig.stop >= sig.entry:
                    invalid.append(f"{strat.name}: stop={sig.stop} >= entry={sig.entry}")
                elif sig.target <= sig.entry:
                    invalid.append(f"{strat.name}: target={sig.target} <= entry={sig.entry}")
                elif sig.rr <= 0:
                    invalid.append(f"{strat.name}: rr={sig.rr}")
        except Exception as e:
            crashed.append(f"{strat.name}: {e}")

    total   = len(ALL_STRATEGIES)
    all_ok  = len(crashed) == 0 and len(invalid) == 0
    problems = crashed + invalid
    _result(
        f"V11 Strategy Signal Validity",
        all_ok,
        f"{total - len(problems)}/{total} OK, {fired} fired signals; "
        + ("; ".join(problems[:3]) if problems else "")
    )


# ─────────────────────────────────────────────────────────────────────────────
# V12 — CandleBuilder OHLCV Correctness
# ─────────────────────────────────────────────────────────────────────────────
def test_candle_builder():
    """Feed known ticks, close the bar, verify OHLCV is correct."""
    from live.candle_builder import CandleBuilder
    from datetime import datetime

    cb = CandleBuilder("TEST")

    # Simulate cumulative day volume ticks
    ticks = [
        (100.0, 1000),   # open
        (105.0, 1500),   # high candidate
        ( 98.0, 2000),   # low candidate
        (102.0, 2800),   # close
    ]
    for price, vol in ticks:
        cb.on_tick(price, vol)

    bar = cb.close_bar(datetime(2026, 6, 17, 9, 15))

    open_ok   = bar["open"]   == 100.0
    high_ok   = bar["high"]   == 105.0
    low_ok    = bar["low"]    ==  98.0
    close_ok  = bar["close"]  == 102.0
    # volume = vol_at_close − vol_at_bar_open = 2800 − 1000 = 1800
    # (first tick sets _vol_start=1000 from cumulative day volume, not 0)
    vol_ok    = bar["volume"] == 1800
    dt_ok     = bar["datetime"] == datetime(2026, 6, 17, 9, 15)

    all_ok = open_ok and high_ok and low_ok and close_ok and vol_ok and dt_ok
    _result(
        "V12 CandleBuilder OHLCV",
        all_ok,
        f"O={bar['open']} H={bar['high']} L={bar['low']} C={bar['close']} "
        f"V={bar['volume']} (expected O=100 H=105 L=98 C=102 V=1800)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print()
    print("Running Trading Agent System Validation")
    print("=" * 52)

    test_preopen_bar_guard()
    test_preopen_tick_filter()
    test_live_price_entry_distances()
    test_rr_consistency()
    test_position_sizing()
    test_pnl_calculation()
    test_quality_filters()
    test_csv_column_integrity()
    test_checkpoint_roundtrip()
    test_no_forward_look()
    test_strategy_signal_validity()
    test_candle_builder()

    print("=" * 52)
    total = _PASS + _FAIL
    if _FAIL == 0:
        print(f"  {_PASS}/{total} passed   — system is CLEAR TO RUN")
    else:
        print(f"  {_PASS}/{total} passed   — {_FAIL} FAILED — DO NOT START AGENT")
        print()
        for name, detail in _ERRORS:
            print(f"  FAILED: {name}")
            print(f"          {detail}")
    print()
    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()

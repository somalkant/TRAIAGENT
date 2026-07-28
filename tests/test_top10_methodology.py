"""
Unit tests for the three post-live-review methodology filters:
regime gate (#3), pullback entry (#4), mid-session time-stop (#5).
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.base import Signal
from backtester.engine import _simulate_outcome
from top10_backtest import regime
from top10_backtest.engine import _before_min_entry
from top10_backtest.entry_filter import pullback_level, apply_pullback
from top10_backtest.simulate import simulate_outcome_top10


class TestMinEntryGate:
    def test_opening_candle_is_before_cutoff(self):
        # default cutoff is 09:30 — 09:15/09:20/09:25 should be gated out
        assert _before_min_entry("09:15")
        assert _before_min_entry("09:20")
        assert _before_min_entry("09:25")

    def test_at_or_after_cutoff_allowed(self):
        assert not _before_min_entry("09:30")
        assert not _before_min_entry("10:15")

    def test_blank_signal_time_not_gated(self):
        assert not _before_min_entry("")


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bars(rows, day=date(2026, 1, 5), start="09:15"):
    """rows = list of (open, high, low, close, volume); one 5-min bar each from start."""
    h, m = map(int, start.split(":"))
    t0 = datetime(day.year, day.month, day.day, h, m)
    out = []
    for i, (o, hi, lo, c, v) in enumerate(rows):
        out.append({"datetime": t0 + timedelta(minutes=5 * i),
                    "open": o, "high": hi, "low": lo, "close": c, "volume": v})
    return pd.DataFrame(out)


# ─────────────────────────────────────────────────────────────────────────────
# regime
# ─────────────────────────────────────────────────────────────────────────────

class TestRegime:
    def test_unknown_before_decision_time(self):
        bars = _bars([(100, 101, 99, 100, 1000)] * 8)
        assert regime.classify_regime(bars, "09:30") == regime.UNKNOWN

    def test_unknown_when_empty(self):
        assert regime.classify_regime(pd.DataFrame(), "10:00") == regime.UNKNOWN

    def test_trend_up(self):
        # OR (first 3 bars) tops out ~102; price then climbs and holds above OR high & VWAP
        rows = [(100, 102, 99, 101, 1000), (101, 102, 100, 101, 1000), (101, 102, 100, 101, 1000)]
        rows += [(102, 105, 102, 104, 1200), (104, 108, 104, 107, 1300), (107, 111, 107, 110, 1400)]
        bars = _bars(rows)
        assert regime.classify_regime(bars, "09:45") == regime.TREND_UP

    def test_trend_down(self):
        rows = [(100, 101, 98, 99, 1000), (99, 100, 98, 99, 1000), (99, 100, 98, 99, 1000)]
        rows += [(98, 98, 95, 96, 1200), (96, 96, 92, 93, 1300), (93, 93, 89, 90, 1400)]
        bars = _bars(rows)
        assert regime.classify_regime(bars, "09:45") == regime.TREND_DOWN

    def test_chop_inside_opening_range(self):
        # price oscillates inside the opening range — neither above OR high nor below OR low
        rows = [(100, 103, 97, 100, 1000)] * 3
        rows += [(100, 102, 98, 99, 1000), (99, 102, 98, 101, 1000), (101, 102, 98, 100, 1000)]
        bars = _bars(rows)
        assert regime.classify_regime(bars, "09:45") == regime.CHOP

    def test_strategy_allowed_unknown_allows_all(self):
        for name in ("ORB-15", "VWAP-REV", "FAILED-BO"):
            assert regime.strategy_allowed(name, "LONG", regime.UNKNOWN)
            assert regime.strategy_allowed(name, "SHORT", regime.UNKNOWN)

    def test_strategy_allowed_chop_reversion_only(self):
        assert regime.strategy_allowed("VWAP-REV", "LONG", regime.CHOP)      # reversion
        assert not regime.strategy_allowed("ORB-15", "LONG", regime.CHOP)    # momentum blocked
        assert regime.strategy_allowed("FAILED-BO", "SHORT", regime.CHOP)    # agnostic always

    def test_strategy_allowed_trend_up_momentum_long_only(self):
        assert regime.strategy_allowed("ORB-15", "LONG", regime.TREND_UP)
        assert not regime.strategy_allowed("ORB-15", "SHORT", regime.TREND_UP)   # don't fight trend
        assert not regime.strategy_allowed("VWAP-REV", "LONG", regime.TREND_UP)  # reversion blocked
        assert regime.strategy_allowed("FAILED-BD", "LONG", regime.TREND_UP)     # agnostic always

    def test_strategy_allowed_trend_down_momentum_short_only(self):
        assert regime.strategy_allowed("SUPERTREND", "SHORT", regime.TREND_DOWN)
        assert not regime.strategy_allowed("SUPERTREND", "LONG", regime.TREND_DOWN)


# ─────────────────────────────────────────────────────────────────────────────
# pullback entry
# ─────────────────────────────────────────────────────────────────────────────

class TestPullback:
    def test_pullback_level_long(self):
        # entry 100, stop 96 -> 0.33 back toward stop = 100 - 0.33*4 = 98.68
        assert pullback_level(100, 96, 1, 0.33) == pytest.approx(98.68)

    def test_pullback_level_short(self):
        # entry 100, stop 104 -> 0.33 above = 100 + 0.33*4 = 101.32
        assert pullback_level(100, 104, -1, 0.33) == pytest.approx(101.32)

    def test_long_pullback_reached_enters_better_price(self):
        sig = Signal("ORB-15", 1, entry=100, target=106, stop=96, signal_time="09:45")
        # bars after 09:45: first dips to 98.5 (below the 98.68 level) -> retest hit
        rows = [(100, 101, 99.5, 100, 1000),   # 09:15..(pre-signal filler)
                (100, 100.5, 98.4, 99, 1000)]  # 09:20 -> low 98.4 <= 98.68
        bars = _bars(rows, start="09:45")
        out = apply_pullback(sig, bars, fraction=0.33, max_bars=6)
        assert out is not None
        assert out.entry == pytest.approx(98.68)          # entered at the retest level, better than 100
        assert out.stop == 96 and out.target == 106       # structural levels unchanged
        assert out.signal_time == "09:50"                 # moved to the retest bar

    def test_long_pullback_never_comes_skips(self):
        sig = Signal("ORB-15", 1, entry=100, target=106, stop=96, signal_time="09:45")
        # price runs away up, never dips to 98.68
        rows = [(100, 101, 99.9, 100.5, 1000), (100.5, 103, 100.4, 102, 1000),
                (102, 104, 101.5, 103, 1000)]
        bars = _bars(rows, start="09:45")
        assert apply_pullback(sig, bars, fraction=0.33, max_bars=6) is None

    def test_no_lookahead_only_bars_after_signal(self):
        sig = Signal("ORB-15", 1, entry=100, target=106, stop=96, signal_time="09:45")
        # the ONLY bar dipping to the level is labelled 09:45 (the signal bar itself) -> must be ignored
        rows = [(100, 100.5, 98.0, 100, 1000),   # 09:45 signal bar, low 98 (ignored)
                (100, 101, 99.9, 100.5, 1000)]   # 09:50, never reaches level
        bars = _bars(rows, start="09:45")
        assert apply_pullback(sig, bars, fraction=0.33, max_bars=6) is None


# ─────────────────────────────────────────────────────────────────────────────
# mid-session time-stop + parity
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulate:
    def _daylong(self, base_rows, direction):
        # pad out to a full session so TIME_EXIT paths are reachable
        return _bars(base_rows)

    def test_parity_with_shared_simulator_when_timestop_off(self):
        scenarios = [
            (Signal("X", 1, entry=100, target=103, stop=98, signal_time="09:15"),
             [(100, 100, 100, 100, 1), (100, 103, 100, 102, 1), (102, 104, 101, 103, 1)]),
            (Signal("X", -1, entry=100, target=97, stop=102, signal_time="09:15"),
             [(100, 100, 100, 100, 1), (100, 100, 96, 98, 1), (98, 99, 97, 98, 1)]),
            (Signal("X", 1, entry=100, target=110, stop=90, signal_time="09:15"),
             [(100, 100, 100, 100, 1), (100, 101, 99, 100, 1), (100, 101, 100, 100, 1)]),
        ]
        for sig, rows in scenarios:
            bars = _bars(rows)
            base = _simulate_outcome(sig, bars)
            mine = simulate_outcome_top10(sig, bars, timestop_enabled=False)
            assert mine == base

    def test_timestop_flattens_a_trade_going_nowhere(self):
        sig = Signal("X", 1, entry=100, target=110, stop=90, signal_time="09:15")
        # entry bar then 3 flat bars near 100 -> after 3 bars, favourable ~0 < 0.5*10=5 => TIME_STOP
        rows = [(100, 100, 100, 100, 1)] + [(100, 100.4, 99.6, 100, 1)] * 4
        bars = _bars(rows)
        out = simulate_outcome_top10(sig, bars, timestop_enabled=True, timestop_bars=3, timestop_min_r=0.5)
        assert out["exit_reason"] == "TIME_STOP"

    def test_timestop_leaves_a_working_trade_alone(self):
        sig = Signal("X", 1, entry=100, target=110, stop=90, signal_time="09:15")
        # by bar 3 the trade is at +6 (>= 0.5*10=5) so it must NOT be time-stopped
        rows = [(100, 100, 100, 100, 1), (100, 103, 100, 102, 1),
                (102, 105, 101, 104, 1), (104, 107, 103, 106, 1), (106, 108, 105, 107, 1)]
        bars = _bars(rows)
        out = simulate_outcome_top10(sig, bars, timestop_enabled=True, timestop_bars=3, timestop_min_r=0.5)
        assert out["exit_reason"] != "TIME_STOP"

    def test_target_hit_takes_precedence_over_timestop(self):
        sig = Signal("X", 1, entry=100, target=103, stop=90, signal_time="09:15")
        # hits target on the checkpoint bar -> TARGET_HIT, not TIME_STOP
        rows = [(100, 100, 100, 100, 1)] * 3 + [(100, 104, 100, 103, 1)]
        bars = _bars(rows)
        out = simulate_outcome_top10(sig, bars, timestop_enabled=True, timestop_bars=3, timestop_min_r=0.5)
        assert out["exit_reason"] == "TARGET_HIT"

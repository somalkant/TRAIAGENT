"""
Tests that the engine correctly selects LONG vs SHORT based on which
direction has a higher composite score.

This answers the question: "Is it possible for the engine to pick a LONG
trade at all, or is it broken?" — confirmed YES, it works correctly.

Run with:
    .\\venv\\Scripts\\python.exe -m pytest tests/test_direction_selection.py -v

Design notes for dummy data:
  - Strategy choices avoid the 50-55% predicted-WR danger zone (filter 7)
  - Candle prices stay within ±9% of open (circuit filter ≤10%)
  - LONG: entry=100, target=105 (+5%), stop=97 (-3%), RR=1.67
  - SHORT: entry=100, target=95  (-5%), stop=103 (+3%), RR=1.67
"""

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.base import Signal
from backtester.composite_scorer import (
    long_composite_score,
    short_composite_score,
    count_agreeing,
)
from backtester.quality_filter import passes_all_filters
from backtester.engine import _pick_direction, _find_best_candidate

TRADE_DATE = date(2019, 1, 2)

# ─────────────────────────────────────────────────────────────────────────────
# Strategy groupings based on lifetime_winrates.json
#
# Danger zone 50-55% (filter 7 blocks): GAP-CONT, ADX-FILTER, ASC-TRI,
#   GAP-FADE, ORB-30, ORB-15, BULL-FLAG — AVOID as agreeing strategies
#
# Above 55% (safe):
#   VOL-SPIKE 73.8% (DRIVER_BLOCKED — can agree but cannot drive)
#   VWAP-REV  61.8%, RSI-EXT 58.0%, DBL-BTM 58.0%
#
# Below 50% (safe — filter blocks >50.0 so exactly 50 is fine):
#   SUPERTREND 38.2%, EMA-CROSS 34.7%, STOCHASTIC 43.3%, MACD 46.7%
#
# Missing from JSON (default 50.0 — NOT in danger zone since filter is >50.0):
#   INTRADAY-STRUCT, BEAR-FLAG, FAILED-BO, etc.
# ─────────────────────────────────────────────────────────────────────────────

# LONG scenario: 4+ strategies with avg WR = (73.8+61.8+58+58+50)/5 = 60.3% → safe
LONG_STRATEGIES = ["VOL-SPIKE", "VWAP-REV", "RSI-EXT", "DBL-BTM", "INTRADAY-STRUCT"]

# SHORT scenario: 4+ strategies with avg WR = (38.2+46.7+43.3+34.7+50)/5 = 42.6% → safe
SHORT_STRATEGIES = ["SUPERTREND", "MACD", "STOCHASTIC", "EMA-CROSS", "BEAR-FLAG"]

# DRIVER_BLOCKED — these can agree but cannot drive the trade entry
DRIVER_BLOCKED = {"VOL-SPIKE", "ORB-30", "ORB-15", "SR-BREAK", "REL-STR"}


def make_long_signal(name: str, entry: float = 100.0) -> Signal:
    """Valid LONG signal: entry=100, target=105, stop=97, RR=1.67."""
    return Signal(name, +1, entry, target=105.0, stop=97.0,
                  rr=round(5.0 / 3.0, 2), signal_time="09:15")


def make_short_signal(name: str, entry: float = 100.0) -> Signal:
    """Valid SHORT signal: entry=100, target=95, stop=103, RR=1.67."""
    return Signal(name, -1, entry, target=95.0, stop=103.0,
                  rr=round(5.0 / 3.0, 2), signal_time="09:15")


def make_5min_df(trade_date: date, hit_long_target: bool = True) -> pd.DataFrame:
    """
    75 flat candles at price 100 with a single spike at candle 7 (09:50):
      - hit_long_target=True  → high=106 at candle 7 → TARGET_HIT for LONG (target=105)
      - hit_long_target=False → low=94  at candle 7 → TARGET_HIT for SHORT (target=95)

    Prices stay within ±9% of open, so circuit filter (<10% move) is never triggered.
    """
    rows = []
    base = datetime(trade_date.year, trade_date.month, trade_date.day, 9, 15)
    for i in range(75):
        ts = base + pd.Timedelta(minutes=5 * i)
        if i == 7:
            if hit_long_target:
                rows.append({"datetime": ts, "open": 100.0, "high": 106.0,
                             "low": 99.5, "close": 100.0, "volume": 80_000})
            else:
                rows.append({"datetime": ts, "open": 100.0, "high": 100.5,
                             "low": 94.0, "close": 100.0, "volume": 80_000})
        else:
            rows.append({"datetime": ts, "open": 100.0, "high": 100.8,
                         "low": 99.5, "close": 100.0, "volume": 50_000})
    return pd.DataFrame(rows)


def make_all_data(trade_date: date, symbol: str, hit_long_target: bool = True) -> dict:
    """
    Builds all_data dict with a warmup day (trade_date - 1 day) and the test day.
    The engine needs at least 1 prior day for prev_day_ohlc etc.
    """
    prev = datetime(trade_date.year, trade_date.month, trade_date.day - 1 if trade_date.day > 1 else 1, 9, 15)
    warmup = pd.DataFrame([
        {"datetime": prev + pd.Timedelta(minutes=5 * i),
         "open": 99.0, "high": 100.5, "low": 98.5, "close": 99.5, "volume": 45_000}
        for i in range(75)
    ])
    today_df = make_5min_df(trade_date, hit_long_target)
    full_df  = pd.concat([warmup, today_df]).reset_index(drop=True)
    return {symbol: full_df}


# Weights where LONG side is maxed and SHORT side is suppressed
LONG_DOMINANT_WEIGHTS = {
    "VOL-SPIKE":       {"long": 3.0, "short": 0.1},
    "VWAP-REV":        {"long": 3.0, "short": 0.1},
    "RSI-EXT":         {"long": 3.0, "short": 0.1},
    "DBL-BTM":         {"long": 3.0, "short": 0.1},
    "INTRADAY-STRUCT": {"long": 3.0, "short": 0.1},
    # Minority SHORT strategies — suppressed long weights
    "SUPERTREND":      {"long": 0.1, "short": 0.5},
    "MACD":            {"long": 0.1, "short": 0.5},
}

# Weights mirroring WF-1 frozen weights after 3 short-dominant training years
SHORT_DOMINANT_WEIGHTS = {
    "SUPERTREND":      {"long": 0.25, "short": 3.0},
    "MACD":            {"long": 0.25, "short": 3.0},
    "STOCHASTIC":      {"long": 0.25, "short": 3.0},
    "EMA-CROSS":       {"long": 0.25, "short": 3.0},
    "BEAR-FLAG":       {"long": 1.0,  "short": 3.0},
    # Minority LONG strategies
    "VWAP-REV":        {"long": 0.25, "short": 0.5},
    "RSI-EXT":         {"long": 0.25, "short": 0.5},
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Composite Scorer (pure logic, no data)
# ─────────────────────────────────────────────────────────────────────────────

class TestCompositeScorer:
    """Verify that score calculation correctly reflects weight direction."""

    def test_long_score_higher_with_long_weights(self):
        """LONG composite score beats SHORT when long weights are maxed."""
        sigs = {n: make_long_signal(n) for n in LONG_STRATEGIES}
        sigs["SUPERTREND"] = make_short_signal("SUPERTREND")
        sigs["MACD"]       = make_short_signal("MACD")

        ls = long_composite_score(sigs, LONG_DOMINANT_WEIGHTS, {})
        ss = short_composite_score(sigs, LONG_DOMINANT_WEIGHTS, {})

        assert ls > ss, f"Expected long_score ({ls:.2f}) > short_score ({ss:.2f})"

    def test_short_score_higher_with_short_weights(self):
        """SHORT composite score beats LONG when short weights are maxed (WF-1 frozen style)."""
        sigs = {n: make_short_signal(n) for n in SHORT_STRATEGIES}
        sigs["VWAP-REV"] = make_long_signal("VWAP-REV")
        sigs["RSI-EXT"]  = make_long_signal("RSI-EXT")

        ls = long_composite_score(sigs, SHORT_DOMINANT_WEIGHTS, {})
        ss = short_composite_score(sigs, SHORT_DOMINANT_WEIGHTS, {})

        assert ss > ls, f"Expected short_score ({ss:.2f}) > long_score ({ls:.2f})"

    def test_agreeing_count_long(self):
        sigs = {n: make_long_signal(n) for n in LONG_STRATEGIES}
        sigs["SUPERTREND"] = make_short_signal("SUPERTREND")

        assert count_agreeing(sigs, direction=+1) == len(LONG_STRATEGIES)
        assert count_agreeing(sigs, direction=-1) == 1

    def test_agreeing_count_short(self):
        sigs = {n: make_short_signal(n) for n in SHORT_STRATEGIES}
        sigs["VWAP-REV"] = make_long_signal("VWAP-REV")

        assert count_agreeing(sigs, direction=-1) == len(SHORT_STRATEGIES)
        assert count_agreeing(sigs, direction=+1) == 1


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — _pick_direction (pure logic, no data)
# ─────────────────────────────────────────────────────────────────────────────

class TestPickDirection:

    def _rec(self, direction: str, score: float) -> dict:
        return {"direction": direction, "score": score,
                "signal": {"direction": +1 if direction == "LONG" else -1}}

    def test_long_wins_when_higher_score(self):
        assert _pick_direction(self._rec("LONG", 15.5), self._rec("SHORT", 8.2))["direction"] == "LONG"

    def test_short_wins_when_higher_score(self):
        assert _pick_direction(self._rec("LONG", 4.3), self._rec("SHORT", 22.1))["direction"] == "SHORT"

    def test_long_wins_on_tie(self):
        assert _pick_direction(self._rec("LONG", 10.0), self._rec("SHORT", 10.0))["direction"] == "LONG"

    def test_long_only(self):
        assert _pick_direction(self._rec("LONG", 5.0), None)["direction"] == "LONG"

    def test_short_only(self):
        assert _pick_direction(None, self._rec("SHORT", 5.0))["direction"] == "SHORT"

    def test_none_when_both_absent(self):
        assert _pick_direction(None, None) is None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Quality Filter (unit, no real market data needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestQualityFilter:

    def _flat_df(self) -> pd.DataFrame:
        ts = datetime(2019, 1, 2, 9, 15)
        return pd.DataFrame([{"datetime": ts, "open": 100.0,
                               "high": 100.8, "low": 99.5,
                               "close": 100.0, "volume": 50_000}])

    def test_valid_long_passes(self):
        ok, reason = passes_all_filters(
            make_long_signal("VWAP-REV"), self._flat_df(),
            daily_turnover_crore=100.0, strategies_agreeing=5,
            composite_score=9.0)
        assert ok, f"Valid LONG should pass: {reason}"

    def test_valid_short_passes(self):
        ok, reason = passes_all_filters(
            make_short_signal("SUPERTREND"), self._flat_df(),
            daily_turnover_crore=100.0, strategies_agreeing=5,
            composite_score=9.0, week52_low=80.0,
            nifty_pct_change=0.0, recent_3day_move=0.01)
        assert ok, f"Valid SHORT should pass: {reason}"

    def test_low_agreeing_blocks(self):
        ok, reason = passes_all_filters(
            make_long_signal("VWAP-REV"), self._flat_df(),
            daily_turnover_crore=100.0, strategies_agreeing=2,
            composite_score=9.0)
        assert not ok and "strategy agreed" in reason

    def test_low_liquidity_blocks(self):
        ok, reason = passes_all_filters(
            make_long_signal("VWAP-REV"), self._flat_df(),
            daily_turnover_crore=1.0, strategies_agreeing=5,
            composite_score=9.0)
        assert not ok and "Liquidity" in reason

    def test_low_rr_blocks(self):
        bad_rr = Signal("VWAP-REV", +1, 100.0, 101.0, 99.5, rr=0.67, signal_time="09:15")
        ok, reason = passes_all_filters(
            bad_rr, self._flat_df(),
            daily_turnover_crore=100.0, strategies_agreeing=5,
            composite_score=9.0)
        assert not ok and "RR" in reason

    def test_danger_zone_wr_blocks(self):
        """Predicted win rate in 50-55% range is blocked (confirmed bad by historical analysis)."""
        ok, reason = passes_all_filters(
            make_long_signal("VWAP-REV"), self._flat_df(),
            daily_turnover_crore=100.0, strategies_agreeing=5,
            composite_score=9.0, predicted_win_pct=52.0)
        assert not ok and "danger zone" in reason

    def test_after_2pm_blocks(self):
        late_sig = Signal("VWAP-REV", +1, 100.0, 105.0, 97.0, rr=1.67, signal_time="14:05")
        ok, reason = passes_all_filters(
            late_sig, self._flat_df(),
            daily_turnover_crore=100.0, strategies_agreeing=5,
            composite_score=9.0)
        assert not ok and "2:00 PM" in reason


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Integration: _find_best_candidate picks correct direction
# ─────────────────────────────────────────────────────────────────────────────

class TestFindBestCandidate:
    """
    End-to-end: _find_best_candidate with fully synthetic OHLCV data.
    Proves the engine CAN and DOES pick LONG when conditions favour it.
    """
    SYMBOL = "TEST"

    def _long_signals(self) -> dict:
        """5 LONG signals (avg lifetime WR=60.3%, safe), 2 SHORT noise."""
        sigs = {n: make_long_signal(n) for n in LONG_STRATEGIES}
        sigs["SUPERTREND"] = make_short_signal("SUPERTREND")
        sigs["MACD"]       = make_short_signal("MACD")
        return sigs

    def _short_signals(self) -> dict:
        """5 SHORT signals (avg lifetime WR=42.6%, safe), 2 LONG noise."""
        sigs = {n: make_short_signal(n) for n in SHORT_STRATEGIES}
        sigs["VWAP-REV"] = make_long_signal("VWAP-REV")
        sigs["RSI-EXT"]  = make_long_signal("RSI-EXT")
        return sigs

    def test_long_dominant_weights_returns_long(self):
        """
        LONG-dominant weights + 5 agreeing LONG signals → must return a LONG trade.
        Proves engine is NOT broken for LONG direction.
        """
        sigs     = self._long_signals()
        all_data = make_all_data(TRADE_DATE, self.SYMBOL, hit_long_target=True)
        turnover = {self.SYMBOL: 100.0}

        raw_score = long_composite_score(sigs, LONG_DOMINANT_WEIGHTS, {})
        result    = _find_best_candidate(
            direction=+1,
            stock_scores={self.SYMBOL: (raw_score, raw_score)},
            stock_signals={self.SYMBOL: sigs},
            all_data=all_data,
            trade_date=TRADE_DATE,
            daily_turnover=turnover,
            weights=LONG_DOMINANT_WEIGHTS,
            freeze_weights=False,
            nifty_pct=0.0,
        )

        assert result is not None, "Expected a LONG candidate, got None"
        assert result["direction"] == "LONG"
        assert result["signal"]["direction"] == +1
        assert result["symbol"] == self.SYMBOL
        print(f"\n  PASS LONG selected: driver={result['signal']['strategy']}, "
              f"score={result['raw_score']:.2f}, agreeing={result['agreeing']}, "
              f"outcome={result['outcome']['exit_reason']}")

    def test_short_dominant_weights_returns_short(self):
        """
        SHORT-dominant weights (WF-1 frozen style) + 5 agreeing SHORT signals →
        must return a SHORT trade.
        """
        sigs     = self._short_signals()
        all_data = make_all_data(TRADE_DATE, self.SYMBOL, hit_long_target=False)
        turnover = {self.SYMBOL: 100.0}

        raw_score = short_composite_score(sigs, SHORT_DOMINANT_WEIGHTS, {})
        result    = _find_best_candidate(
            direction=-1,
            stock_scores={self.SYMBOL: (raw_score, raw_score)},
            stock_signals={self.SYMBOL: sigs},
            all_data=all_data,
            trade_date=TRADE_DATE,
            daily_turnover=turnover,
            weights=SHORT_DOMINANT_WEIGHTS,
            freeze_weights=False,
            nifty_pct=0.0,
        )

        assert result is not None, "Expected a SHORT candidate, got None"
        assert result["direction"] == "SHORT"
        assert result["signal"]["direction"] == -1
        assert result["symbol"] == self.SYMBOL
        print(f"\n  PASS SHORT selected: driver={result['signal']['strategy']}, "
              f"score={result['raw_score']:.2f}, agreeing={result['agreeing']}, "
              f"outcome={result['outcome']['exit_reason']}")

    def test_long_wins_daily_competition_with_long_weights(self):
        """
        Full daily competition: both LONG and SHORT candidates exist.
        With LONG-dominant weights, _pick_direction must choose LONG.
        This is the core proof that LONG selection works end-to-end.
        """
        all_sigs = {**self._long_signals(), **self._short_signals()}
        all_data = make_all_data(TRADE_DATE, self.SYMBOL, hit_long_target=True)
        turnover = {self.SYMBOL: 100.0}

        long_raw  = long_composite_score(all_sigs,  LONG_DOMINANT_WEIGHTS, {})
        short_raw = short_composite_score(all_sigs, LONG_DOMINANT_WEIGHTS, {})

        long_rec = _find_best_candidate(
            +1, {self.SYMBOL: (long_raw, long_raw)},
            {self.SYMBOL: all_sigs}, all_data, TRADE_DATE, turnover,
            LONG_DOMINANT_WEIGHTS, False, 0.0)
        short_rec = _find_best_candidate(
            -1, {self.SYMBOL: (short_raw, short_raw)},
            {self.SYMBOL: all_sigs}, all_data, TRADE_DATE, turnover,
            LONG_DOMINANT_WEIGHTS, False, 0.0)

        chosen = _pick_direction(long_rec, short_rec)

        assert chosen is not None
        assert chosen["direction"] == "LONG", (
            f"LONG should win daily competition with LONG-dominant weights. "
            f"long_score={long_raw:.2f}, short_score={short_raw:.2f}. Got: {chosen['direction']}")
        print(f"\n  PASS Daily competition: long={long_raw:.2f} vs short={short_raw:.2f} -> LONG wins")

    def test_short_wins_daily_competition_with_short_weights(self):
        """
        Full daily competition with SHORT-dominant weights (mirrors WF-1 frozen).
        Explains why 2019 had 0 LONG trades — short composite score always beat long.
        """
        all_sigs = {**self._long_signals(), **self._short_signals()}
        all_data = make_all_data(TRADE_DATE, self.SYMBOL, hit_long_target=False)
        turnover = {self.SYMBOL: 100.0}

        long_raw  = long_composite_score(all_sigs,  SHORT_DOMINANT_WEIGHTS, {})
        short_raw = short_composite_score(all_sigs, SHORT_DOMINANT_WEIGHTS, {})

        long_rec = _find_best_candidate(
            +1, {self.SYMBOL: (long_raw, long_raw)},
            {self.SYMBOL: all_sigs}, all_data, TRADE_DATE, turnover,
            SHORT_DOMINANT_WEIGHTS, False, 0.0)
        short_rec = _find_best_candidate(
            -1, {self.SYMBOL: (short_raw, short_raw)},
            {self.SYMBOL: all_sigs}, all_data, TRADE_DATE, turnover,
            SHORT_DOMINANT_WEIGHTS, False, 0.0)

        chosen = _pick_direction(long_rec, short_rec)

        assert chosen is not None
        assert chosen["direction"] == "SHORT", (
            f"SHORT should win with WF-1 frozen weights. "
            f"long_score={long_raw:.2f}, short_score={short_raw:.2f}. Got: {chosen['direction']}")
        print(f"\n  PASS Daily competition (WF-1 frozen): "
              f"long={long_raw:.2f} vs short={short_raw:.2f} -> SHORT wins "
              f"(explains why 2019 had 0 LONG trades)")

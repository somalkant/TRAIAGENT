"""
Unit tests for top10_backtest/strength.py::classify_strength.

Run with:
    .\\venv\\Scripts\\python.exe -m pytest tests/test_strength.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from top10_backtest.strength import classify_strength, MIN_HISTORY_DAYS


def _bars(day: str, times: list[str], opens, highs, lows, closes, volumes) -> pd.DataFrame:
    return pd.DataFrame({
        "datetime": [pd.Timestamp(f"{day} {t}:00") for t in times],
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes,
    })


def _flat_history(n_days: int, signal_time: str, volume: float, high: float, low: float,
                   close: float, start_day: int = 1) -> pd.DataFrame:
    """n_days of unremarkable same-time-of-day bars, one row per day, for the
    reference distribution, plus a same-day preceding bar so true-range has a
    prev_close to compare against."""
    frames = []
    for d in range(start_day, start_day + n_days):
        day = f"2026-01-{d:02d}"
        frames.append(_bars(
            day, ["09:15", signal_time],
            opens=[close, close], highs=[close + 0.5, high], lows=[close - 0.5, low],
            closes=[close, close], volumes=[volume, volume],
        ))
    return pd.concat(frames, ignore_index=True)


def test_unrated_when_history_too_short():
    today = _bars("2026-02-01", ["09:15", "09:45"], [100, 102], [100.5, 102.5],
                   [99.5, 101.5], [100, 102], [1000, 5000])
    history = _flat_history(MIN_HISTORY_DAYS - 5, "09:45", volume=1000, high=100.5, low=99.5, close=100)
    tier = classify_strength(1, today, history, "09:45")
    assert tier == "UNRATED"


def test_strong_long_high_volume_wide_range_close_at_high():
    signal_time = "09:45"
    history = _flat_history(MIN_HISTORY_DAYS + 5, signal_time, volume=1000, high=100.5, low=99.5, close=100)
    # Signal bar: much bigger volume, much wider range, closes right at the high (LONG-favorable).
    today = _bars("2026-02-01", ["09:15", signal_time], [100, 100], [100.5, 106],
                   [99.5, 99], [100, 105.9], [1000, 20000])
    tier = classify_strength(1, today, history, signal_time)
    assert tier == "STRONG"


def test_low_long_thin_volume_narrow_range_close_mid_bar():
    signal_time = "09:45"
    history = _flat_history(MIN_HISTORY_DAYS + 5, signal_time, volume=5000, high=102, low=98, close=100)
    # Signal bar: much smaller volume, narrow range, closes in the middle (no conviction).
    today = _bars("2026-02-01", ["09:15", signal_time], [100, 100], [100.5, 100.3],
                   [99.5, 99.9], [100, 100.1], [5000, 200])
    tier = classify_strength(1, today, history, signal_time)
    assert tier == "LOW"


def test_short_direction_favors_close_near_low():
    signal_time = "09:45"
    history = _flat_history(MIN_HISTORY_DAYS + 5, signal_time, volume=1000, high=100.5, low=99.5, close=100)
    # Wide range, high volume, closes at the LOW — favorable for a SHORT.
    today = _bars("2026-02-01", ["09:15", signal_time], [100, 100], [100, 101],
                   [94, 94], [100, 94.1], [1000, 20000])
    tier = classify_strength(-1, today, history, signal_time)
    assert tier == "STRONG"


def test_future_bars_after_signal_time_do_not_leak_into_classification():
    """The backtest hands strategies the WHOLE day's bars, not just bars up
    to the signal — classify_strength must self-truncate. Appending extreme
    bars AFTER signal_time must not change the result at all."""
    signal_time = "09:45"
    history = _flat_history(MIN_HISTORY_DAYS + 5, signal_time, volume=5000, high=102, low=98, close=100)
    today_no_future = _bars("2026-02-01", ["09:15", signal_time], [100, 100], [100.5, 100.3],
                             [99.5, 99.9], [100, 100.1], [5000, 200])
    today_with_future = pd.concat([
        today_no_future,
        _bars("2026-02-01", ["09:50", "09:55"], [100.1, 150], [200, 200],
              [100, 100], [150, 150], [999999, 999999]),
    ], ignore_index=True)

    tier_without = classify_strength(1, today_no_future, history, signal_time)
    tier_with    = classify_strength(1, today_with_future, history, signal_time)
    assert tier_without == tier_with == "LOW"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

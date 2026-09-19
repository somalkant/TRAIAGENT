"""
One definition of a valid 5-minute bar file, used by every writer and reader.

Canonical format (all years, stocks and indices):
  * `datetime` is naive IST wall-clock time (no tz label). The historical Kite download was
    tz-aware (+05:30) while the daily Groww EOD is naive; mixing the two broke concatenation
    (backtester silently dropped 2026) and, before 2026-07-21, shifted appended bars by +5:30.
  * Only regular-session bars: labels 09:15 .. 15:25 (75 bars). The broker API sometimes returns
    pre-open (09:00-09:10) and post-close (15:30+) bars; they are not part of the session and
    change "first candle", "day open" and "previous close" for every strategy that uses them.
  * Sorted by time, one row per timestamp.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

SESSION_FIRST = time(9, 15)      # label of the first 5-min bar
SESSION_LAST = time(15, 25)      # label of the last 5-min bar (15:25-15:30)
_FIRST_MIN = SESSION_FIRST.hour * 60 + SESSION_FIRST.minute
_LAST_MIN = SESSION_LAST.hour * 60 + SESSION_LAST.minute


def to_naive_ist(s: pd.Series) -> pd.Series:
    """tz-aware -> converted to IST and the label dropped; naive -> assumed IST already."""
    s = pd.to_datetime(s)
    if s.dt.tz is not None:
        s = s.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return s


def session_mask(dt: pd.Series) -> pd.Series:
    m = dt.dt.hour * 60 + dt.dt.minute
    return (m >= _FIRST_MIN) & (m <= _LAST_MIN)


def normalize_bars(df: pd.DataFrame, keep: str = "last") -> pd.DataFrame:
    """Canonicalise a bar frame (see module docstring). `keep` decides which duplicate survives
    when two rows share a timestamp — 'last' lets freshly downloaded bars replace stored ones."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out["datetime"] = to_naive_ist(out["datetime"])
    out = out[session_mask(out["datetime"])]
    out = out.sort_values("datetime", kind="stable").drop_duplicates(subset=["datetime"], keep=keep)
    for col in ("open", "high", "low", "close"):
        if col in out:
            out[col] = out[col].astype(float)
    if "volume" in out:
        out["volume"] = out["volume"].fillna(0).astype("int64")
    return out.reset_index(drop=True)


def audit(df: pd.DataFrame) -> dict:
    """Counts of everything normalize_bars would change, plus days that look corrupted by the old
    +5:30 append bug (afternoon 14:45-14:55 identical to that day's 09:15-09:25 = shifted copy)."""
    t = to_naive_ist(df["datetime"])
    m = (t.dt.hour * 60 + t.dt.minute).values
    sess = session_mask(t).values
    w = pd.DataFrame({"d": t.dt.date.values, "m": m, "o": df["open"].values, "h": df["high"].values,
                      "l": df["low"].values, "c": df["close"].values})[sess]
    am = w[w.m.isin([555, 560, 565])].set_index(["d", "m"])
    pm = w[w.m.isin([885, 890, 895])].assign(m=lambda x: x.m - 330).set_index(["d", "m"])
    both = am.join(pm, rsuffix="_pm", how="inner")
    same = ((both.o - both.o_pm).abs() < 1e-9) & ((both.h - both.h_pm).abs() < 1e-9) &            ((both.l - both.l_pm).abs() < 1e-9) & ((both.c - both.c_pm).abs() < 1e-9)
    moving = (both.h > both.l)                          # frozen-price days (circuit / no trades) are
    per_day = pd.DataFrame({"same": same, "moving": moving}).groupby(level="d").agg(   # legitimately identical
        same=("same", "sum"), moving=("moving", "sum"), n=("same", "size"))
    # the +5:30 bug always left its junk copies AFTER 15:30 on the same day — require that evidence
    junk_days = set(t[(~sess) & ((t.dt.hour * 60 + t.dt.minute) >= 15 * 60 + 30)].dt.date)
    corrupt = sorted(d for d in per_day[(per_day.n == 3) & (per_day.same == 3) & (per_day.moving > 0)].index
                     if d in junk_days)
    return {
        "tz_aware": pd.to_datetime(df["datetime"]).dt.tz is not None,
        "out_of_session": int((~sess).sum()),
        "out_of_session_days": sorted(set(t[~sess].dt.date)),
        "duplicates": int(t.duplicated().sum()),
        "corrupt_afternoon_days": corrupt,
    }

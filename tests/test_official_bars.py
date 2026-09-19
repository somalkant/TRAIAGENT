"""Official-candle reconciliation (live/data_manager.reconcile_official) and canonical bars (data_pipeline/bars)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_pipeline.bars import normalize_bars, audit                 # noqa: E402
from live.data_manager import LiveDataManager                       # noqa: E402
from live.instrument_map import NIFTY50_TOKEN                       # noqa: E402

DAY = datetime(2026, 9, 16)


def _candles(n, start="09:15", vol=1000, extra_pre=False, extra_post=False):
    t0 = DAY.replace(hour=int(start[:2]), minute=int(start[3:]))
    out = [{"date": t0 + timedelta(minutes=5 * i), "open": 100 + i, "high": 101 + i, "low": 99 + i,
            "close": 100.5 + i, "volume": vol} for i in range(n)]
    if extra_pre:
        out.insert(0, {"date": DAY.replace(hour=9, minute=5), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 5})
    if extra_post:
        out.append({"date": DAY.replace(hour=15, minute=35), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 5})
    return out


class FakeClient:
    def __init__(self, table):
        self.table = table                      # token -> candles | Exception

    def historical_data(self, instrument_token, from_date, to_date, interval):
        r = self.table.get(instrument_token, [])
        if isinstance(r, Exception):
            raise r
        return [c for c in r if from_date <= c["date"] <= to_date]


def _dm_with_tick_bars():
    dm = LiveDataManager(symbols=["AAA", "BBB", "CCC"], imap={"AAA": 1, "BBB": 2, "CCC": 3})
    for s in ("AAA", "BBB", "CCC"):
        # tick-built bars: zero volume, wrong opening price
        dm._builders[s].replace_closed([{"datetime": DAY.replace(hour=9, minute=15) + timedelta(minutes=5 * i),
                                          "open": 90.0, "high": 101, "low": 99, "close": 100.5, "volume": 0}
                                         for i in range(3)])
        dm._builders[s].on_tick(123.0, 10)      # a bar in progress, must survive
    return dm


def test_reconcile_replaces_with_official_and_falls_back():
    upto = DAY.replace(hour=9, minute=25)       # third bar just closed
    client = FakeClient({1: _candles(3, extra_pre=True, extra_post=True),   # ok (junk bars filtered)
                         2: _candles(2),                                     # 09:25 candle not published yet
                         3: RuntimeError("429 rate limited"),                # API error
                         NIFTY50_TOKEN: _candles(3)})
    dm = _dm_with_tick_bars()
    dm.attach_official_source(client)
    st = dm.reconcile_official(upto, budget_sec=5, workers=4, max_rps=100)
    assert st["n"] == 4 and st["ok"] == 2 and st["fallback"] == 2
    a = dm.get_today("AAA")
    assert list(a.open) == [100, 101, 102] and list(a.volume) == [1000] * 3          # official, session-only
    assert a.datetime.iloc[0] == DAY.replace(hour=9, minute=15)
    assert list(dm.get_today("BBB").volume) == [0, 0, 0]                            # kept live-built bars
    assert list(dm.get_today("CCC").volume) == [0, 0, 0]
    assert st["zero_vol_fixed"] == 3 and st["open_fixed"] == 1
    assert dm._builders["AAA"]._o == 123.0                                           # bar in progress untouched


def test_no_source_is_a_noop():
    dm = _dm_with_tick_bars()
    assert dm.reconcile_official(DAY.replace(hour=9, minute=25))["n"] == 0


def test_normalize_bars_canonical():
    raw = pd.DataFrame(_candles(3, extra_pre=True, extra_post=True)).rename(columns={"date": "datetime"})
    raw["datetime"] = pd.to_datetime(raw["datetime"]).dt.tz_localize("Asia/Kolkata")          # tz-aware input
    dup = raw[raw.datetime.dt.strftime("%H:%M") == "09:20"].assign(close=999.0)             # later duplicate wins
    out = normalize_bars(pd.concat([raw, dup]))
    assert out["datetime"].dt.tz is None
    assert out["datetime"].dt.strftime("%H:%M").tolist() == ["09:15", "09:20", "09:25"]
    assert out.close.iloc[1] == 999.0                      # the later row for 09:20 replaced the earlier one
    a = audit(raw)
    assert a["tz_aware"] and a["out_of_session"] == 2


def test_audit_flags_shifted_afternoon_copy():
    bars = []
    for i in range(75):
        t = DAY.replace(hour=9, minute=15) + timedelta(minutes=5 * i)
        bars.append({"datetime": t, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i, "volume": 1})
    df = pd.DataFrame(bars)
    for i in range(3):                               # 14:45-14:55 overwritten by +5:30 copies of 09:15-09:25
        df.loc[df.datetime == DAY.replace(hour=14, minute=45 + 5 * i), ["open", "high", "low", "close"]] = \
            df.loc[df.datetime == DAY.replace(hour=9, minute=15 + 5 * i), ["open", "high", "low", "close"]].values
    junk = pd.DataFrame([{"datetime": DAY.replace(hour=15, minute=30) + timedelta(minutes=5 * i), "open": 1, "high": 2,
                          "low": 1, "close": 1, "volume": 1} for i in range(3)])
    assert audit(pd.concat([df, junk]))["corrupt_afternoon_days"] == [DAY.date()]
    assert audit(df)["corrupt_afternoon_days"] == []                 # no junk evidence -> not flagged


def test_eod_append_writes_canonical_file(tmp_path):
    """The EOD writer must turn a tz-aware stored file + naive new rows (with pre-open / post-close
    bars) into one canonical file, and must not shift anything by +5:30."""
    from data_pipeline.downloader import _append_parquet
    stored = pd.DataFrame(_candles(3)).rename(columns={"date": "datetime"})
    stored["datetime"] = pd.to_datetime(stored["datetime"]).dt.tz_localize("Asia/Kolkata")   # Kite-style
    stored["symbol"] = "AAA"
    f = tmp_path / "AAA.parquet"
    stored.to_parquet(f, index=False)
    new = pd.DataFrame(_candles(2, start="09:25", vol=7, extra_pre=True, extra_post=True)).rename(columns={"date": "datetime"})
    new["symbol"] = "AAA"                                                                    # Groww-style naive
    _append_parquet(f, new)
    out = pd.read_parquet(f)
    assert out["datetime"].dt.tz is None
    assert out["datetime"].dt.strftime("%H:%M").tolist() == ["09:15", "09:20", "09:25", "09:30"]
    assert out.loc[out.datetime.dt.strftime("%H:%M") == "09:25", "volume"].item() == 7     # new row replaced old


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))

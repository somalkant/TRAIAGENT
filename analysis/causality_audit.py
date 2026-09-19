"""Causality audit of all 37 strategies: do they only use bars that exist at signal_time?

    venv\Scripts\python.exe -m analysis.causality_audit     (~6 min on 11 cores)

For sampled (stock, day): compute each strategy on the full day and on today's bars
truncated after every bar k (bars 09:15..k, i.e. what live sees once bar k has closed).
For each full-day signal S (signal_time T), classify:
  exact    : first visible at bar T and stays identical afterwards      -> causal, fire-once
  delayed  : identical S appears only at a bar AFTER T (lag>0)           -> signal_time is back-dated
  never    : S never appears on truncated data                           -> uses bars beyond 14:00 / later data
  unstable : S appears then changes/disappears                           -> mind-changing
Also counts 'early_other': truncated data fired a DIFFERENT signal first (live would have seen it).
"""
import warnings; warnings.filterwarnings("ignore")
import sys, random, time
from multiprocessing import Pool
ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import pandas as pd
from pathlib import Path


def key(s):
    if s is None or s.direction == 0 or s.entry <= 0: return None
    return (s.direction, round(float(s.entry), 3), round(float(s.target), 3), round(float(s.stop), 3), s.signal_time)


def work(args):
    sym, days = args
    import warnings; warnings.filterwarnings("ignore")
    from strategies import ALL_STRATEGIES
    from backtester.engine import _get_prev_day_ohlc
    df = pd.read_parquet(f"{ROOT}/data/stocks/2026/{sym}.parquet"); df["datetime"] = pd.to_datetime(df["datetime"])
    nifty = pd.read_parquet(f"{ROOT}/data/index/2026/NIFTY50.parquet"); nifty["datetime"] = pd.to_datetime(nifty["datetime"])
    if nifty.datetime.dt.tz is not None:
        nifty["datetime"] = nifty.datetime.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    out = []
    for day in days:
        today = df[df.datetime.dt.date == day].reset_index(drop=True)
        if len(today) < 57: continue
        hist = df[df.datetime.dt.date < day]; prev = _get_prev_day_ohlc(hist, day)
        nt = nifty[nifty.datetime.dt.date == day]
        for st in ALL_STRATEGIES:
            try: fk = key(st.generate_signal(today, hist, prev, nt, day))
            except Exception as e: fk = ("ERR", type(e).__name__)
            seq = []
            for k in range(1, 58):                                 # through the 13:55 bar
                tr = today.iloc[:k]; last = tr.datetime.iloc[-1]
                try: sk = key(st.generate_signal(tr, hist, prev, nt[nt.datetime <= last], day))
                except Exception as e: sk = ("ERR", type(e).__name__)
                seq.append((last.strftime("%H:%M"), sk))
            out.append((st.name, sym, str(day), fk, seq))
    return out


def classify(fk, seq):
    first_other = next(((t, s) for t, s in seq if s is not None and s != fk), None)
    if fk is None:
        return ("nofire_full_but_trunc_fired" if first_other else "nofire"), 0, first_other
    if isinstance(fk, tuple) and fk and fk[0] == "ERR":
        return "error_full", 0, None
    T = fk[4]
    if not T or T >= "14:00":
        return "late_or_untimed", 0, first_other
    vis = [i for i, (t, s) in enumerate(seq) if s == fk]
    if not vis:
        return "never", 0, first_other
    i0 = vis[0]; t0 = seq[i0][0]
    stable = all(s == fk for _, s in seq[i0:])
    lag = (int(t0[:2]) * 60 + int(t0[3:])) - (int(T[:2]) * 60 + int(T[3:]))
    early = next(((t, s) for t, s in seq[:i0] if s is not None), None)
    if not stable: return "unstable", lag, early
    return ("exact" if lag == 0 else "delayed"), lag, early


if __name__ == "__main__":
    random.seed(11)
    syms = sorted(p.stem for p in Path(ROOT, "data/stocks/2026").glob("*.parquet"))
    jobs = []
    for sym in random.sample(syms, 36):
        d = pd.read_parquet(f"{ROOT}/data/stocks/2026/{sym}.parquet", columns=["datetime"])
        days = sorted(pd.to_datetime(d.datetime).dt.date.unique())[30:]
        jobs.append((sym, random.sample(days, 5)))
    t0 = time.time()
    with Pool(11) as p:
        res = [r for chunk in p.map(work, jobs) for r in chunk]
    print(f"{len(res)} (strategy,stock,day) cases in {time.time()-t0:.0f}s\n")
    rows = []
    for name, sym, day, fk, seq in res:
        cls, lag, early = classify(fk, seq)
        rows.append(dict(strategy=name, sym=sym, day=day, cls=cls, lag=lag, early_other=early is not None,
                         full_T=(fk[4] if isinstance(fk, tuple) and len(fk) == 5 else None),
                         full_dir=(fk[0] if isinstance(fk, tuple) and len(fk) == 5 else None)))
    R = pd.DataFrame(rows)
    R.to_csv(Path(ROOT, "reports", "gap_analysis", "causality_audit.csv"), index=False)
    fired = R[~R.cls.isin(["nofire", "error_full"])]
    tab = pd.crosstab(fired.strategy, fired.cls)
    for c in ["exact", "delayed", "unstable", "never", "late_or_untimed", "nofire_full_but_trunc_fired"]:
        if c not in tab: tab[c] = 0
    tab["fired"] = tab.sum(axis=1)
    tab["causal_%"] = (100 * tab.exact / tab[["exact", "delayed", "unstable", "never"]].sum(axis=1).clip(lower=1)).round(0)
    lagd = R[R.cls == "delayed"].groupby("strategy").lag.median()
    tab["median_lag_min"] = lagd
    tab["early_other"] = R[R.early_other].groupby("strategy").size()
    tab = tab.fillna(0).sort_values("causal_%")
    print(tab[["fired", "exact", "delayed", "median_lag_min", "unstable", "never", "late_or_untimed",
               "nofire_full_but_trunc_fired", "early_other", "causal_%"]].to_string())
    print("\nerrors on full day:", R[R.cls == "error_full"].strategy.value_counts().to_dict())

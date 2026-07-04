"""
Replay historical backtest trades (paper_trades.csv) through the profit-lock
exit policy (live/exit_policy.py: LONG trades whose target is >=
min_target_pct away from entry get capped at a flat cap_pct gain instead of
the original target; SHORT trades are never affected) to see whether it
would have improved win rate / P&L.

Read-only analysis — does not touch engine.py checkpoints, weights, or
paper_trades.csv. Re-derives each trade's exit using the actual 5-min parquet
bars for that symbol/date, then recomputes P&L with the same cost model used
by the backtester.

Usage:
    python scripts/replay_profit_lock.py --years 2025 2026
"""

import argparse
from datetime import time as dtime

import pandas as pd

from config.settings import (
    STOCKS_DIR, PAPER_TRADES_FILE,
    PROFIT_LOCK_MIN_TARGET_PCT, PROFIT_LOCK_CAP_PCT,
)
from backtester.cost_model import net_pnl

_parquet_cache: dict[tuple[int, str], pd.DataFrame] = {}


def _load_symbol_year(year: int, symbol: str) -> pd.DataFrame | None:
    key = (year, symbol)
    if key in _parquet_cache:
        return _parquet_cache[key]
    path = STOCKS_DIR / str(year) / f"{symbol}.parquet"
    if not path.exists():
        _parquet_cache[key] = None
        return None
    df = pd.read_parquet(path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    _parquet_cache[key] = df
    return df


def _parse_time(s: str) -> dtime:
    try:
        h, m = map(int, str(s).split(":"))
        return dtime(h, m)
    except Exception:
        return dtime(9, 15)


def _result_label(exit_reason: str, pnl: float) -> str:
    if exit_reason == "TARGET_HIT":
        return "EXACT_WIN"
    return "WIN" if pnl > 0 else "LOSS"


def _simulate_with_profit_lock(entry: float, target: float, stop: float,
                               direction: int, sig_time_str: str,
                               today_bars: pd.DataFrame,
                               min_target_pct: float = PROFIT_LOCK_MIN_TARGET_PCT,
                               cap_pct: float = PROFIT_LOCK_CAP_PCT) -> dict:
    """Bar-based replay of one trading day with target/stop/profit-lock checks.
    Mirrors backtester.engine._simulate_outcome, plus the profit-lock cap:
    LONG trades whose target is >= min_target_pct away from entry get capped
    at a flat cap_pct gain instead of the original (larger) target -- matches
    live/exit_policy.py's evaluate_profit_lock(). SHORT trades are never
    affected. Checked in TARGET > PROFIT_LOCK > STOP order per bar, consistent
    with the existing optimistic same-bar-touch convention used for
    TARGET_HIT vs STOP_HIT."""
    sig_dt  = _parse_time(sig_time_str)
    exit_dt = dtime(15, 15)

    target_dist   = target - entry
    lock_eligible = (direction == 1 and entry > 0 and target_dist > 0
                     and (target_dist / entry * 100) >= min_target_pct)
    cap_level     = entry * (1 + cap_pct / 100)

    exit_price, exit_reason, exit_time = entry, "TIME_EXIT", "15:15"

    for _, c in today_bars.iterrows():
        t = pd.Timestamp(c["datetime"]).time()
        if t <= sig_dt:
            continue
        if t >= exit_dt:
            exit_price, exit_reason, exit_time = float(c["open"]), "TIME_EXIT", t.strftime("%H:%M")
            break

        high, low, close = float(c["high"]), float(c["low"]), float(c["close"])

        if direction == 1:
            if high >= target:
                exit_price, exit_reason, exit_time = target, "TARGET_HIT", t.strftime("%H:%M")
                break
            if lock_eligible and high >= cap_level:
                exit_price, exit_reason, exit_time = cap_level, "PROFIT_LOCK", t.strftime("%H:%M")
                break
            if low <= stop:
                exit_price, exit_reason, exit_time = stop, "STOP_HIT", t.strftime("%H:%M")
                break
            exit_price, exit_time = close, t.strftime("%H:%M")
        else:
            if low <= target:
                exit_price, exit_reason, exit_time = target, "TARGET_HIT", t.strftime("%H:%M")
                break
            if high >= stop:
                exit_price, exit_reason, exit_time = stop, "STOP_HIT", t.strftime("%H:%M")
                break
            exit_price, exit_time = close, t.strftime("%H:%M")

    return {"exit_price": exit_price, "exit_reason": exit_reason, "exit_time": exit_time}


def _summarize(rows: list[dict], label: str) -> dict:
    n = len(rows)
    if n == 0:
        return {"label": label, "trades": 0}
    wins = sum(1 for r in rows if r["result"] in ("EXACT_WIN", "WIN"))
    total_pnl = sum(r["pnl_rs"] for r in rows)
    return {
        "label":     label,
        "trades":    n,
        "win_rate":  round(wins / n * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl":   round(total_pnl / n, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025, 2026])
    ap.add_argument("--min-target-pct", type=float, default=PROFIT_LOCK_MIN_TARGET_PCT)
    ap.add_argument("--cap-pct", type=float, default=PROFIT_LOCK_CAP_PCT)
    ap.add_argument("--show-changed", type=int, default=40, help="max changed-trade rows to print")
    ap.add_argument("--file", type=str, default=str(PAPER_TRADES_FILE), help="path to trade log CSV")
    args = ap.parse_args()

    df = pd.read_csv(args.file, on_bad_lines="skip")
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df = df[df["year"].isin(args.years)].reset_index(drop=True)
    print(f"Loaded {len(df)} trades for years {args.years} from {args.file}")
    print(f"Policy: LONG only, min_target_pct={args.min_target_pct}%  cap_pct={args.cap_pct}%\n")

    baseline_rows, lock_rows = [], []
    changed = []
    rescues, clipped = [], []
    missing_data = 0

    for _, row in df.iterrows():
        entry  = float(row["entry_price"])
        target = float(row["target"])
        stop   = float(row["stop_loss"])
        shares = int(row["quantity"])
        direction = 1 if target > entry else -1
        trade_date = row["date"].date()
        year   = trade_date.year
        symbol = row["symbol"]

        baseline_pnl = float(row["pnl_rs"])
        baseline_rows.append({
            "result": row["result"],
            "pnl_rs": baseline_pnl,
        })

        bars = _load_symbol_year(year, symbol)
        if bars is None:
            missing_data += 1
            lock_rows.append({"result": row["result"], "pnl_rs": baseline_pnl})
            continue
        today_bars = bars[bars["datetime"].dt.date == trade_date].reset_index(drop=True)
        if today_bars.empty:
            missing_data += 1
            lock_rows.append({"result": row["result"], "pnl_rs": baseline_pnl})
            continue

        outcome = _simulate_with_profit_lock(entry, target, stop, direction,
                                             row["signal_time"], today_bars,
                                             min_target_pct=args.min_target_pct,
                                             cap_pct=args.cap_pct)
        pnl = net_pnl(entry, outcome["exit_price"], shares, direction=direction)
        result = _result_label(outcome["exit_reason"], pnl)
        lock_rows.append({"result": result, "pnl_rs": pnl})

        if outcome["exit_reason"] != row["exit_reason"]:
            delta = pnl - baseline_pnl
            entry_row = {
                "date": trade_date, "symbol": symbol, "direction": "LONG" if direction == 1 else "SHORT",
                "baseline_reason": row["exit_reason"], "baseline_pnl": baseline_pnl,
                "lock_reason": outcome["exit_reason"], "lock_pnl": round(pnl, 2),
            }
            changed.append(entry_row)
            if row["result"] == "LOSS":
                rescues.append(delta)
            else:
                clipped.append(delta)

    print(f"Missing parquet/day data for {missing_data} trades (kept baseline outcome as fallback)\n")

    for yr in args.years:
        yr_mask = (df["year"] == yr).values
        b = [r for r, m in zip(baseline_rows, yr_mask) if m]
        l = [r for r, m in zip(lock_rows, yr_mask) if m]
        sb, sl = _summarize(b, "baseline"), _summarize(l, "profit_lock")
        print(f"--- {yr} ---")
        if sb["trades"]:
            print(f"  baseline    : {sb['trades']} trades | win rate {sb['win_rate']}% | P&L Rs {sb['total_pnl']:,.0f}")
            print(f"  profit_lock : {sl['trades']} trades | win rate {sl['win_rate']}% | P&L Rs {sl['total_pnl']:,.0f}"
                  f"  (delta Rs {sl['total_pnl'] - sb['total_pnl']:+,.0f})")
        else:
            print("  0 trades")

    sb_all, sl_all = _summarize(baseline_rows, "baseline"), _summarize(lock_rows, "profit_lock")
    print(f"\n--- COMBINED {args.years} ---")
    print(f"  baseline    : {sb_all['trades']} trades | win rate {sb_all.get('win_rate')}% | "
          f"P&L Rs {sb_all.get('total_pnl'):,.0f} | avg Rs {sb_all.get('avg_pnl'):,.0f}")
    print(f"  profit_lock : {sl_all['trades']} trades | win rate {sl_all.get('win_rate')}% | "
          f"P&L Rs {sl_all.get('total_pnl'):,.0f} | avg Rs {sl_all.get('avg_pnl'):,.0f}  "
          f"(delta Rs {sl_all['total_pnl'] - sb_all['total_pnl']:+,.0f})")

    print(f"\n{len(changed)} trades had a different exit under profit-lock "
          f"({len(rescues)} rescues from a baseline LOSS, {len(clipped)} clipped from a baseline WIN/EXACT_WIN):")
    if rescues:
        print(f"  rescues : total Rs {sum(rescues):+,.0f}  avg Rs {sum(rescues)/len(rescues):+,.0f}")
    if clipped:
        print(f"  clipped : total Rs {sum(clipped):+,.0f}  avg Rs {sum(clipped)/len(clipped):+,.0f}")

    for c in changed[:args.show_changed]:
        print(f"  {c['date']} {c['symbol']:<12} {c['direction']:<5} "
              f"{c['baseline_reason']:<12} Rs{c['baseline_pnl']:>10,.0f}  ->  "
              f"{c['lock_reason']:<12} Rs{c['lock_pnl']:>10,.0f}")
    if len(changed) > args.show_changed:
        print(f"  ... and {len(changed) - args.show_changed} more")


if __name__ == "__main__":
    main()

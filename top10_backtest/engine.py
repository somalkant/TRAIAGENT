"""
Top-10 backtest engine — day-by-day simulation over an arbitrary date range.

Reuses the exact target/stop/15:15-time-exit bar-scan mechanic from
backtester/engine.py (_simulate_outcome) and its today/prev-day slicing
helpers (_get_today, _get_prev_day_ohlc) — those are pure data mechanics with
no dependency on the old composite-scoring/adaptive-weight system. Everything
else here (universe rules, capital sizing, trade selection, output) is new.
"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd
from tqdm import tqdm

from config.settings import STOCKS_DIR, INDEX_DIR, CHECKPOINT_DIR
from backtester.engine import _simulate_outcome, _get_today, _get_prev_day_ohlc
from backtester.cost_model import net_pnl

from top10_backtest.strategies import TOP10_STRATEGIES, TOP10_NAMES
from top10_backtest.universe import long_universe, short_universe
from top10_backtest.capital import size, StrategyLedger
from top10_backtest.costs import cost_breakdown
from top10_backtest.output import append_trades

log = logging.getLogger(__name__)

_CHECKPOINT_FILE = CHECKPOINT_DIR / "top10_backtest_checkpoint.json"


def run(start_date: date, end_date: date, resume: bool = True) -> None:
    all_data, nifty_all = _preload_range(start_date, end_date)
    if not all_data:
        raise RuntimeError(f"No stock data found for range {start_date}..{end_date}")

    days = _trading_days(all_data, start_date, end_date)
    if not days:
        raise RuntimeError(f"No trading days found in range {start_date}..{end_date}")

    last_done = _load_checkpoint() if resume else None
    if last_done:
        days = [d for d in days if d > last_done]
        log.info(f"Resuming after checkpoint {last_done} — {len(days)} trading days remaining")

    ledger = StrategyLedger(TOP10_NAMES)

    for trade_date in tqdm(days, desc="Top-10 backtest"):
        long_syms  = long_universe(all_data, trade_date)
        short_syms = short_universe()
        active     = long_syms | short_syms

        if active:
            symbol_slices = _build_symbol_slices(all_data, active, trade_date)
            nifty_today = _get_today(nifty_all, trade_date) if nifty_all is not None else pd.DataFrame()

            day_rows = []
            for strategy in TOP10_STRATEGIES:
                long_pick, short_pick = _scan_strategy(
                    strategy, symbol_slices, long_syms, short_syms, nifty_today, trade_date
                )
                for side, pick in (("LONG", long_pick), ("SHORT", short_pick)):
                    if pick is None:
                        continue
                    symbol, today, sig = pick
                    row = _build_trade_row(trade_date, side, strategy.name, symbol, today, sig)
                    if row is not None:
                        day_rows.append(row)
                        ledger.record(strategy.name, side, row["net_pnl_rs"])

            if day_rows:
                append_trades(day_rows)

        _save_checkpoint(trade_date)

    log.info("Top-10 backtest complete.")
    for name, stats in ledger.summary().items():
        log.info(
            f"  {name}: LONG {stats['long_trades']}t Rs{stats['long_pnl']:,.0f} | "
            f"SHORT {stats['short_trades']}t Rs{stats['short_pnl']:,.0f}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Per-day scanning
# ─────────────────────────────────────────────────────────────────────────────

def _build_symbol_slices(all_data: dict, active: set[str], trade_date: date) -> dict:
    """One (today, history, prev_day) slice per active symbol, computed once/day."""
    slices = {}
    for symbol in active:
        df = all_data.get(symbol)
        if df is None:
            continue
        today = _get_today(df, trade_date)
        if today.empty:
            continue
        history  = df[df["datetime"].dt.date < trade_date]
        prev_day = _get_prev_day_ohlc(history, trade_date)
        slices[symbol] = (today, history, prev_day)
    return slices


def _scan_strategy(strategy, symbol_slices: dict, long_syms: set[str], short_syms: set[str],
                    nifty_today: pd.DataFrame, trade_date: date):
    """
    Runs the strategy once per active symbol. A BUY signal only counts if the
    symbol is in the LONG universe; a SELL signal only counts if it's in the
    SHORT (F&O) universe — a signal on a symbol outside the relevant universe
    is not tradeable under this test's rules and is discarded.
    """
    long_candidates, short_candidates = [], []
    for symbol, (today, history, prev_day) in symbol_slices.items():
        eligible_long  = symbol in long_syms
        eligible_short = symbol in short_syms
        if not eligible_long and not eligible_short:
            continue

        sig = strategy.generate_signal(today, history, prev_day, nifty_today, trade_date)
        if not sig.is_valid:
            continue

        if sig.direction == 1 and eligible_long:
            long_candidates.append((symbol, today, sig))
        elif sig.direction == -1 and eligible_short:
            short_candidates.append((symbol, today, sig))

    return _first_chrono(long_candidates), _first_chrono(short_candidates)


def _first_chrono(candidates: list) -> tuple | None:
    """First signal by signal_time; ties broken by symbol alphabetical order."""
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[2].signal_time or "99:99", c[0]))
    return candidates[0]


def _build_trade_row(trade_date: date, side: str, strategy_name: str, symbol: str,
                      today_5min: pd.DataFrame, sig) -> dict | None:
    outcome = _simulate_outcome(sig, today_5min)
    qty, notional = size(sig.entry)
    if qty <= 0:
        return None

    net   = net_pnl(sig.entry, outcome["exit_price"], qty, direction=sig.direction)
    gross = (outcome["exit_price"] - sig.entry) * qty * sig.direction
    cost  = round(gross - net, 2)
    costs = cost_breakdown(sig.entry, outcome["exit_price"], qty, sig.direction)

    result = "EXACT_WIN" if outcome["exit_reason"] == "TARGET_HIT" else ("WIN" if net > 0 else "LOSS")

    return {
        "date": str(trade_date), "side": side, "strategy": strategy_name, "symbol": symbol,
        "signal_time": sig.signal_time, "entry_price": sig.entry, "qty": qty,
        "notional_rs": notional, "stop": sig.stop, "target": sig.target,
        "exit_time": outcome["exit_time"], "exit_price": outcome["exit_price"],
        "exit_reason": outcome["exit_reason"], "result": result,
        "gross_pnl_rs": round(gross, 2), "total_cost_rs": cost,
        "net_pnl_rs": round(net, 2),
        "net_pnl_pct": round(net / notional * 100, 2) if notional else 0.0,
        **{k: round(v, 2) for k, v in costs.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _preload_range(start_date: date, end_date: date) -> tuple[dict, pd.DataFrame | None]:
    """Loads one continuous multi-year window: (start_date.year - 1) warm-up
    through end_date.year, per symbol, deduped and sorted."""
    warmup_year = start_date.year - 1
    years = range(warmup_year, end_date.year + 1)

    all_data: dict[str, pd.DataFrame] = {}
    for y in years:
        yr_dir = STOCKS_DIR / str(y)
        if not yr_dir.exists():
            continue
        for f in yr_dir.glob("*.parquet"):
            try:
                df = pd.read_parquet(f)
                df["datetime"] = pd.to_datetime(df["datetime"])
            except Exception:
                continue
            stem = f.stem
            all_data[stem] = pd.concat([all_data[stem], df]) if stem in all_data else df

    for stem, df in all_data.items():
        all_data[stem] = (df.drop_duplicates("datetime")
                             .sort_values("datetime")
                             .reset_index(drop=True))

    nifty_dfs = []
    for y in years:
        nf = INDEX_DIR / str(y) / "NIFTY50.parquet"
        if nf.exists():
            df = pd.read_parquet(nf)
            df["datetime"] = pd.to_datetime(df["datetime"])
            nifty_dfs.append(df)
    nifty_all = None
    if nifty_dfs:
        nifty_all = (pd.concat(nifty_dfs)
                       .drop_duplicates("datetime")
                       .sort_values("datetime")
                       .reset_index(drop=True))

    log.info(f"Preloaded {len(all_data)} symbols, {warmup_year}-{end_date.year} "
             f"(trading range {start_date}..{end_date})")
    return all_data, nifty_all


def _trading_days(all_data: dict, start_date: date, end_date: date) -> list[date]:
    all_days: set = set()
    for df in all_data.values():
        mask = (df["datetime"].dt.date >= start_date) & (df["datetime"].dt.date <= end_date)
        all_days.update(df.loc[mask, "datetime"].dt.date.unique())
    return sorted(all_days)


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint (resume support for a multi-hour run)
# ─────────────────────────────────────────────────────────────────────────────

def _load_checkpoint() -> date | None:
    if not _CHECKPOINT_FILE.exists():
        return None
    try:
        data = json.loads(_CHECKPOINT_FILE.read_text())
        return date.fromisoformat(data["last_completed_date"])
    except Exception:
        return None


def _save_checkpoint(trade_date: date) -> None:
    _CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CHECKPOINT_FILE.write_text(json.dumps({"last_completed_date": str(trade_date)}))

"""One-off: simulate June 19 scanner with CRAFTSMAN skipped, find next qualifying trade."""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import pandas as pd
import json
from datetime import date
from pathlib import Path
from strategies import ALL_STRATEGIES
from backtester.engine import _best_signal, _predicted_win_pct, _LIFETIME_WR
from backtester.composite_scorer import composite_score, count_agreeing_filtered
from backtester.quality_filter import passes_all_filters
from config.settings import AGREEMENT_MIN_LIFETIME_WR

TRADE_DATE = date(2026, 6, 19)
SKIP = {'CRAFTSMAN'}
MIN_RETURN_PCT = 0.5

WATCHLIST = [
    'ADANIENT','ADANIPORTS','PREMIERENE','PNB','ADANIENSOL','ADANIGREEN','CPPLUS',
    'DIVISLAB','ETERNAL','ICICIBANK','ICICIGI','IDEA','JBCHEPHARM','LAURUSLABS','MRF',
    'SONACOMS','SYRMA','TITAN','ABCAPITAL','ACMESOLAR','ANANTRAJ','APOLLOHOSP','ATGL',
    'ATHERENERG','AXISBANK','BANKINDIA','BHARATFORG','CANBK','CEMPRO','CHENNPETRO',
    'COFORGE','CRAFTSMAN','DELHIVERY','DMART','EMMVEE','ENGINERSIN','GAIL','GRASIM',
    'GROWW','HYUNDAI','ICICIAMC','IGL','INDIANB','LICHSGFIN','LODHA','LTF','MFSL',
    'MPHASIS','NEULANDLAB','OBEROIRLTY','OLAELEC','PAGEIND','PHOENIXLTD','POLYCAB',
    'SCI','SHYAMMETL','TATATECH','TVSMOTOR','WELCORP','ZEEL','ABB','ACUTAAS',
    'ADANIPOWER','ASIANPAINT','AUBANK','BAJFINANCE','BEL','BHARTIARTL','CAMS','CHOLAFIN',
    'COROMANDEL','DLF','ENRIN','GVT&D','HDFCAMC','HDFCBANK','HEROMOTOCO','HFCL',
    'HINDUNILVR','ICICIPRULI','IDFCFIRSTB','INDHOTEL','INDIGO','INDUSINDBK','JINDALSAW',
    'JIOFIN','JSWSTEEL','KOTAKBANK','LUPIN','MANAPPURAM','MANKIND','MAXHEALTH',
    'NAM-INDIA','OLECTRA','PIDILITIND','PRESTIGE','SAREGAMA','SBIN','SHREECEM','SIEMENS',
]


def load_stock(sym):
    frames = []
    for yr in ['2025', '2026']:
        f = Path(f'data/stocks/{yr}/{sym}.parquet')
        if f.exists():
            frames.append(pd.read_parquet(f))
    if not frames:
        return None, None, None
    df = pd.concat(frames).drop_duplicates('datetime').sort_values('datetime')
    df['datetime'] = pd.to_datetime(df['datetime'])
    history = df[df['datetime'].dt.date < TRADE_DATE].copy()
    today   = df[df['datetime'].dt.date == TRADE_DATE].copy()
    prev_day = None
    if not history.empty:
        prev_dates = sorted(history['datetime'].dt.date.unique())
        if prev_dates:
            prev_df = history[history['datetime'].dt.date == prev_dates[-1]]
            prev_day = pd.Series({
                'open':   float(prev_df['open'].iloc[0]),
                'high':   float(prev_df['high'].max()),
                'low':    float(prev_df['low'].min()),
                'close':  float(prev_df['close'].iloc[-1]),
                'volume': int(prev_df['volume'].sum()),
            })
    return history, today, prev_day


print('Loading data...')
stock_data = {}
for sym in WATCHLIST:
    if sym in SKIP:
        continue
    h, t, p = load_stock(sym)
    if h is not None and t is not None and not t.empty:
        stock_data[sym] = (h, t, p)
print(f'Loaded {len(stock_data)} stocks\n')

with open('checkpoints/strategy_weights.json') as f:
    weights = json.load(f)

# Get all unique bar times
all_times = sorted(set(
    ts for sym in stock_data
    for ts in stock_data[sym][1]['datetime'].dt.strftime('%H:%M').unique()
))

found = False
for bar_time in all_times:
    hh, mm = int(bar_time[:2]), int(bar_time[3:])
    if hh < 9 or (hh == 9 and mm < 20):
        continue
    if hh >= 14:
        break

    candidates = []
    for sym, (h, t_full, prev_day) in stock_data.items():
        today_5min = t_full[t_full['datetime'].dt.strftime('%H:%M') <= bar_time].copy()
        if today_5min.empty:
            continue
        try:
            signals = {}
            for strategy in ALL_STRATEGIES:
                sig = strategy.generate_signal(
                    today_5min=today_5min,
                    history_5min=h,
                    prev_day=prev_day,
                    nifty_today=pd.DataFrame(),
                    trade_date=TRADE_DATE,
                )
                if sig and sig.direction != 0:
                    signals[strategy.name] = sig
            if not signals:
                continue
            best_sig = _best_signal(signals, weights, {})
            if best_sig is None or best_sig.direction != 1:
                continue
            score = composite_score(signals, weights, {})
            agreeing = count_agreeing_filtered(signals, +1, _LIFETIME_WR, AGREEMENT_MIN_LIFETIME_WR)
            if agreeing < 4:
                continue
            last_close = float(today_5min['close'].iloc[-1])
            vol_sum = int(today_5min['volume'].sum())
            turnover = last_close * vol_sum / 1e7
            pred_win_pct = _predicted_win_pct(signals, weights, _LIFETIME_WR, direction=+1)
            passes, reason = passes_all_filters(best_sig, today_5min, turnover, agreeing, score, pred_win_pct)
            if not passes:
                continue
            # Apply new guards
            target_dist = best_sig.target - best_sig.entry
            ret_pct = target_dist / best_sig.entry * 100
            stale = last_close >= best_sig.target
            too_small = ret_pct < MIN_RETURN_PCT
            candidates.append({
                'time': bar_time, 'sym': sym, 'score': round(score, 2),
                'agreeing': agreeing, 'strategy': best_sig.strategy,
                'entry': round(best_sig.entry, 2), 'target': round(best_sig.target, 2),
                'stop': round(best_sig.stop, 2), 'rr': round(best_sig.rr, 2),
                'ret_pct': round(ret_pct, 2), 'pred': round(pred_win_pct, 1),
                'stale': stale, 'too_small': too_small,
                'passes_guards': not stale and not too_small,
            })
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: -x['score'])
        for c in candidates[:5]:
            if c['stale']:
                guard_note = ' [SKIP: live already past target]'
            elif c['too_small']:
                guard_note = f' [SKIP: return {c["ret_pct"]}% < 0.5%]'
            else:
                guard_note = ' <<< WOULD TAKE THIS'
            print(
                f"{c['time']} | {c['sym']:12s} | driver={c['strategy']:12s} | "
                f"score={c['score']} agreeing={c['agreeing']} | "
                f"entry={c['entry']} target={c['target']} stop={c['stop']} | "
                f"ret={c['ret_pct']}% RR={c['rr']} pred={c['pred']}%"
                f"{guard_note}"
            )
        if any(c['passes_guards'] for c in candidates):
            found = True
            break
        print()

if not found:
    print('\nNo trade passing all guards found for the full day.')
    print('Summary: all signals that cleared quality filters but failed new guards:')
    # Re-run collecting ALL that cleared quality filters
    all_cleared = []
    for bar_time in all_times:
        hh, mm = int(bar_time[:2]), int(bar_time[3:])
        if hh < 9 or (hh == 9 and mm < 20): continue
        if hh >= 14: break
        for sym, (h, t_full, prev_day) in stock_data.items():
            today_5min = t_full[t_full['datetime'].dt.strftime('%H:%M') <= bar_time].copy()
            if today_5min.empty: continue
            try:
                signals = {}
                for strategy in ALL_STRATEGIES:
                    sig = strategy.generate_signal(
                        today_5min=today_5min, history_5min=h,
                        prev_day=prev_day, nifty_today=pd.DataFrame(), trade_date=TRADE_DATE,
                    )
                    if sig and sig.direction != 0:
                        signals[strategy.name] = sig
                if not signals: continue
                best_sig = _best_signal(signals, weights, {})
                if best_sig is None or best_sig.direction != 1: continue
                score = composite_score(signals, weights, {})
                agreeing = count_agreeing_filtered(signals, +1, _LIFETIME_WR, AGREEMENT_MIN_LIFETIME_WR)
                if agreeing < 4: continue
                last_close = float(today_5min['close'].iloc[-1])
                vol_sum = int(today_5min['volume'].sum())
                turnover = last_close * vol_sum / 1e7
                pred_win_pct = _predicted_win_pct(signals, weights, _LIFETIME_WR, direction=+1)
                passes, _ = passes_all_filters(best_sig, today_5min, turnover, agreeing, score, pred_win_pct)
                if not passes: continue
                ret_pct = (best_sig.target - best_sig.entry) / best_sig.entry * 100
                all_cleared.append({
                    'time': bar_time, 'sym': sym, 'score': round(score,2),
                    'strategy': best_sig.strategy, 'entry': round(best_sig.entry,2),
                    'target': round(best_sig.target,2), 'stop': round(best_sig.stop,2),
                    'rr': round(best_sig.rr,2), 'ret_pct': round(ret_pct,2),
                    'agreeing': agreeing, 'pred': round(pred_win_pct,1),
                    'stale': last_close >= best_sig.target,
                    'too_small': ret_pct < MIN_RETURN_PCT,
                })
            except Exception:
                pass
    # Deduplicate: keep first appearance per symbol
    seen = set()
    unique = []
    for c in sorted(all_cleared, key=lambda x: x['time']):
        if c['sym'] not in seen:
            seen.add(c['sym'])
            unique.append(c)
    if unique:
        print(f'{"Time":6} {"Symbol":12} {"Driver":12} {"Score":6} {"Agr":4} {"Entry":8} {"Target":8} {"Ret%":6} {"RR":5} {"Pred%":6} Note')
        print('-'*100)
        for c in unique:
            note = 'STALE' if c['stale'] else f'ret={c["ret_pct"]}% too small'
            print(f"{c['time']:6} {c['sym']:12} {c['strategy']:12} {c['score']:6} {c['agreeing']:4} {c['entry']:8} {c['target']:8} {c['ret_pct']:6}% {c['rr']:5} {c['pred']:6}%  {note}")
    else:
        print('No other stock cleared quality filters today at all.')

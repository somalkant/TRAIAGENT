"""
Central configuration — all constants for the trading agent.
Import this everywhere: from config.settings import *
"""

from datetime import time

# ─────────────────────────────────────────────
# PHASE DEFINITIONS
# ─────────────────────────────────────────────
LEARNING_START_YEAR = 2016
LEARNING_END_YEAR   = 2026   # WF6 training: 2023-2026 added to learning set

TESTING_START_YEAR  = 2023
TESTING_END_YEAR    = 2026   # YTD

ALL_YEARS = list(range(LEARNING_START_YEAR, TESTING_END_YEAR + 1))

def get_phase(year: int) -> str:
    if year <= LEARNING_END_YEAR:
        return "LEARNING"
    return "TESTING"

# ─────────────────────────────────────────────
# DATA PARAMETERS
# ─────────────────────────────────────────────
DATA_INTERVAL     = "5minute"
CHUNK_DAYS        = 95          # max days per Kite API call for 5-min (safe margin below 100)
RATE_LIMIT_SLEEP  = 0.38        # seconds between API calls (safe below 3 req/sec)
MAX_RETRIES       = 3
RETRY_BACKOFF     = [5, 15, 60] # seconds to wait on retry 1, 2, 3

MARKET_OPEN  = time(9, 15)      # NSE market open
MARKET_CLOSE = time(15, 30)     # NSE market close
CANDLES_PER_DAY  = 75           # (9:15 to 15:30) / 5 min = 75 candles

# ─────────────────────────────────────────────
# CAPITAL & RISK PARAMETERS
# ─────────────────────────────────────────────
CAPITAL               =  10_00_000   # Rs 10,00,000 (10 Lakhs)
MAX_LOSS_PER_TRADE    =    20_000    # Rs 20,000  (2% of capital)
MAX_CONCURRENT_POSITIONS = 1        # Phase 2: 1 trade/day
MAX_POSITION_SIZE     =   5_00_000  # Rs 5,00,000 (50% of capital — conservative single position)

DAILY_LOSS_LIMIT      =   40_000    # Rs 40,000  — pause all recommendations today
MONTHLY_LOSS_LIMIT    =  1_00_000   # Rs 1,00,000 — pause system, flag for review

NO_ENTRY_AFTER        = time(14, 0)  # 2:00 PM IST — no new positions after this
SQUARE_OFF_TARGET     = time(15, 15) # 3:15 PM IST — close all positions

# ─────────────────────────────────────────────
# TRANSACTION COST MODEL
# ─────────────────────────────────────────────
BROKERAGE_PER_LEG  = 20          # Rs 20 per order (Rs 40 round trip)
STT_RATE_SELL      = 0.00025     # 0.025% on sell side (intraday)
EXCHANGE_RATE      = 0.0000345   # 0.00345% per side
SEBI_RATE          = 0.000001    # 0.0001% per side
GST_RATE           = 0.18        # 18% on brokerage + exchange charges
STAMP_RATE_BUY     = 0.00003     # 0.003% on buy side
SLIPPAGE_PER_SIDE  = 0.0005      # 0.05% assumed slippage each side

# ─────────────────────────────────────────────
# FILL TOLERANCE
# ─────────────────────────────────────────────
# Max % away from the decided entry price we walk the order book to fill.
# 0.10% on a ₹1570 entry = ₹1.57 band — takes levels at ₹1569.80,
# ₹1569.90, ₹1570.00 etc rather than stopping at the exact tick.
# Levels beyond this band appear only in the "best available" diagnostic.
FILL_TOLERANCE_PCT = 0.10

def calculate_total_cost(buy_value: float, sell_value: float) -> float:
    brokerage = BROKERAGE_PER_LEG * 2
    stt       = sell_value * STT_RATE_SELL
    exchange  = (buy_value + sell_value) * EXCHANGE_RATE
    sebi      = (buy_value + sell_value) * SEBI_RATE
    gst       = (brokerage + exchange) * GST_RATE
    stamp     = buy_value * STAMP_RATE_BUY
    slippage  = (buy_value + sell_value) * SLIPPAGE_PER_SIDE
    return brokerage + stt + exchange + sebi + gst + stamp + slippage

BREAKEVEN_PCT = 0.0015  # ~0.15% move needed to cover all costs

# ─────────────────────────────────────────────
# QUALITY FILTERS (all 6 must pass to recommend)
# ─────────────────────────────────────────────
LIQUIDITY_MIN_TURNOVER   = 50_00_00_000  # Rs 50 Crore median 20-day daily turnover (Rs 5L position < 1% of daily vol)
MIN_RISK_REWARD          = 1.5    # floor — bad RR<=2 drivers are blocked via DRIVER_BLOCKED, not global threshold
MIN_STRATEGIES_AGREEING  = 4     # raised from 2 — 2-agreement win rate was 32.3% in 2025 (Finding 5)
VOLUME_MULTIPLIER        = 1.5          # current vol > 1.5x same-time-yesterday
MAX_RECOMMENDATIONS      = 3

# Position sizing formula: min(MAX_POSITION_SIZE, MAX_LOSS_PER_TRADE / stop_pct)
def calculate_position_size(stop_loss_pct: float) -> float:
    risk_based = MAX_LOSS_PER_TRADE / stop_loss_pct
    return min(MAX_POSITION_SIZE, risk_based)

# ─────────────────────────────────────────────
# ADAPTIVE WEIGHT SYSTEM
# ─────────────────────────────────────────────
INITIAL_WEIGHT       = 1.0
MIN_WEIGHT           = 0.1    # floor — strategy never fully removed
MAX_WEIGHT           = 3.0    # cap — no single strategy dominates
WEIGHT_UPDATE_EVERY  = 20     # recalculate every N trading days
WEIGHT_SIGNAL_WINDOW = 20     # based on last N signals per strategy

WEIGHT_MULTIPLIERS = {
    "boost":    1.5,   # win_rate > 60%
    "hold":     1.0,   # win_rate 40-60%
    "reduce":   0.5,   # win_rate 30-40%
    "suppress": 0.1,   # win_rate < 30%
}

# Minimum trades in the signal window before a weight update is applied.
# Guards against feedback-loop suppression: a strategy that rarely wins selection
# accumulates sparse data, which can cause premature weight cuts that further
# reduce selection frequency — a self-fulfilling spiral.
MIN_TRADES_FOR_WEIGHT_UPDATE = 10

REVIVAL_WEIGHT = 0.5   # weight reset when suppressed strategy's regime returns

# Win rate thresholds for weight update
WIN_RATE_BOOST    = 0.60
WIN_RATE_HOLD_LOW = 0.40
WIN_RATE_REDUCE   = 0.30

# ─────────────────────────────────────────────
# REGIME OVERRIDES (applied daily before scoring)
# ─────────────────────────────────────────────
HIGH_VIX_THRESHOLD      = 20    # VIX > 20 → suppress breakout strategies
HIGH_ADX_THRESHOLD      = 25    # ADX > 25 with low VIX → suppress reversion strategies

BREAKOUT_REGIME_MULT    = 0.3   # multiplier on breakout weights in high VIX
REVERSION_REGIME_MULT   = 0.5   # multiplier on reversion weights in low VIX + high ADX

# Strategy categories for regime override
BREAKOUT_STRATEGIES  = ["ORB-15", "ORB-30", "PDH-PDL", "GAP-CONT", "VOL-SPIKE",
                         "SR-BREAK", "FIRST-CANDLE", "EMA-CROSS",
                         "ASC-TRI", "BULL-FLAG",
                         # Phase 2B bearish breakdowns also suppressed in low-VIX trending markets
                         "FAILED-BO", "BEAR-FLAG"]
REVERSION_STRATEGIES = ["VWAP-REV", "RSI-EXT", "BOLLINGER", "GAP-FADE",
                         "VWAP-STDDEV", "STOCHASTIC", "CPR", "CAMARILLA",
                         # Phase 2B mean-reversion shorts
                         "DEAD-CAT", "OPEN-WEAK"]
# Reversal pattern strategies (DBL-BTM, FALL-WEDGE, DBL-TOP, PIN-BAR etc.) deliberately
# excluded from regime lists — they perform best during high-volatility regime changes.

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
from pathlib import Path

BASE_DIR         = Path(__file__).parent.parent
DATA_DIR         = BASE_DIR / "data"
STOCKS_DIR       = DATA_DIR / "stocks"
INDEX_DIR        = DATA_DIR / "index"
CHECKPOINT_DIR   = BASE_DIR / "checkpoints"
MEMORY_DIR       = BASE_DIR / "memory"
NOTEBOOKS_DIR    = BASE_DIR / "notebooks" / "daily"
REPORTS_DIR      = BASE_DIR / "reports"

PROGRESS_FILE    = CHECKPOINT_DIR / "progress.json"
WEIGHTS_FILE     = CHECKPOINT_DIR / "strategy_weights.json"
UNIVERSE_FILE    = BASE_DIR / "config" / "universe.csv"
TRADE_LOG_DIR    = DATA_DIR / "trade_logs"
PAPER_TRADES_FILE           = TRADE_LOG_DIR / "paper_trades.csv"  # Phase 2 unified log
TESTING_MAX_RECOMMENDATIONS = 1       # Phase 2: 1 trade per day
AGREEMENT_MIN_LIFETIME_WR      = 50.0  # SHORT direction gate (keep strict — short WRs are genuinely strong)
AGREEMENT_MIN_LIFETIME_WR_LONG = 40.0  # LONG direction gate — lowered from 50% (bear years 2020-2022 drove most LONG WRs below 50%, causing LONG=[none])
AGREEMENT_MIN_LIFETIME_WR_SHORT = 50.0 # explicit SHORT alias for clarity

# Conviction-based position sizing — scale risk up when a proven strategy drives the trade
CONVICTION_HIGH_WR   = 65.0  # driver lifetime win% >= 65% → 2x risk (VPOC qualifies; VOL-SPIKE blocked despite 73.8%)
CONVICTION_MED_WR    = 55.0  # driver lifetime win% >= 55% → 1.5x risk
CONVICTION_HIGH_MULT = 2.0   # Rs 10k base → Rs 20k risk
CONVICTION_MED_MULT  = 1.5   # Rs 10k base → Rs 15k risk

# ─────────────────────────────────────────────
# PHASE 2B — SHORT SELLING
# ─────────────────────────────────────────────
SHORT_ENABLED          = True
LOWER_CIRCUIT_BUFFER   = 0.02   # skip short if stock within 2% of lower circuit limit
WEEK52_LOW_BUFFER      = 0.05   # skip short if within 5% of 52-week low on a green Nifty day
NIFTY_GREEN_THRESHOLD  = 0.005  # Nifty up >0.5% is "green" for Filter 9
CORP_EVENT_MOVE_PCT    = 0.05   # skip short if stock moved >5% in prior 3 days (news proxy)

# Direction bias: applied when picking between best long and best short candidate
SHORT_REGIME_VIX_MULT      = 1.3   # VIX > HIGH_VIX_THRESHOLD: short_score × 1.3
LONG_REGIME_BULLISH_MULT   = 1.2   # Nifty > +1.5%: long_score × 1.2
SHORT_REGIME_BEARISH_MULT  = 1.2   # Nifty < -1.5%: short_score × 1.2
NIFTY_BULLISH_THRESHOLD    = 1.5   # % change threshold (positive)
NIFTY_BEARISH_THRESHOLD    = -1.5  # % change threshold (negative)

WF_WEIGHTS_DIR = CHECKPOINT_DIR   # where frozen WF weight snapshots are stored

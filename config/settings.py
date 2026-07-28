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

# ─────────────────────────────────────────────
# TOP-10 STRATEGY LIVE AGENT — RISK LIMITS
# ─────────────────────────────────────────────
# Whole-system: same 4%/10% ratios as DAILY_LOSS_LIMIT/MONTHLY_LOSS_LIMIT above,
# scaled to the 10-strategy system's total capital base (10 x Rs 10L = Rs 1Cr).
TOP10_SYSTEM_DAILY_LOSS_LIMIT      =  4_00_000   # Rs 4,00,000
TOP10_SYSTEM_MONTHLY_LOSS_LIMIT    = 10_00_000   # Rs 10,00,000
# Per-strategy, per-side: same ratios applied to each independent Rs 5L side-pool.
TOP10_PER_STRATEGY_DAILY_LOSS_LIMIT    = 20_000   # Rs 20,000 (4% of Rs 5L)
TOP10_PER_STRATEGY_MONTHLY_LOSS_LIMIT  = 50_000   # Rs 50,000 (10% of Rs 5L)

NO_ENTRY_AFTER        = time(14, 0)  # 2:00 PM IST — no new positions after this
SQUARE_OFF_TARGET     = time(15, 15) # 3:15 PM IST — close all positions

# ─────────────────────────────────────────────
# PROFIT LOCK EXIT POLICY (conservative early profit booking, LONG only)
# ─────────────────────────────────────────────
# Only applies to LONG trades whose entry->target distance is >= this many percent.
PROFIT_LOCK_MIN_TARGET_PCT = 2.0
# When it applies, cap the exit at this flat % gain from entry instead of the
# original (larger) target — e.g. target=2%+ away gets capped to a 1% exit.
PROFIT_LOCK_CAP_PCT        = 1.0

# ─────────────────────────────────────────────
# ORDER BOOK FILL SIMULATION (paper trading realism)
# ─────────────────────────────────────────────
# Max % away from the decided entry price we'll still walk the book and
# acquire shares at — e.g. entry=1569.80 + 0.1% = levels up to ~1571.37 count.
# Levels beyond this band are shown as "best available" in logs but not filled
# (we don't chase price indefinitely).
FILL_TOLERANCE_PCT = 0.10

# Top-10 agent uses a wider band — the default 0.10% produced false "not
# filled" reads on 2026-07-15 where real depth existed ~0.17% away from the
# signal price (ample shares, just outside the tight band).
TOP10_FILL_TOLERANCE_PCT = 0.25
# Minimum filled_qty/target_qty ratio to (a) bother committing a candidate at
# the pre-trade gate, and (b) count the position as real once the post-fill
# settle window closes. Below this at settle time, the trade is voided —
# not logged as a completed trade with fictional full-size P&L.
TOP10_MIN_FILL_RATIO = 0.5

# ─────────────────────────────────────────────
# TOP-10 METHODOLOGY IMPROVEMENTS (post-10-session live review)
# ---------------------------------------------------------------------------
# Three independent, individually-toggleable filters added after the first 10
# live sessions showed a 37% win rate at ~1.0 payoff (structurally unprofitable):
# regime-blindness (all strategies firing every day, failing together on the
# same days), chasing (STRONG-tagged extended-bar entries performed WORST), and
# a large dead-trade bucket (44% of trades time-exited near breakeven). Each
# flag can be flipped independently so the backtest can measure its own
# contribution. All default ON — turn any OFF to isolate its effect or revert.
#
# NOTE: these deliberately make the live agent DIVERGE from the pre-existing
# backtest baseline. They are mirrored into top10_backtest/engine.py so the
# same rules can be validated over multi-year history before being trusted.

# ── #6 Minimum entry time: no entries on the opening candle(s) ──
# The single highest-impact, most defensible fix from the live-evidence review.
# 42% of the first month's trades fired on the 09:15 opening candle and lost
# ~Rs 1.46L — essentially the ENTIRE month's loss — at a 31% win rate, while
# 09:20-09:40 entries were near breakeven. The opening candle is gap/liquidity-
# sweep noise; fading or breaking out of it with a fixed % stop gets run over.
# Refusing entries before this time takes the month from -Rs 2.2L to ~breakeven
# on its own (a structural, generalizable rule — not hindsight strategy-picking).
# base.py has a 09:30 warmup but only some strategies honour it; this gate
# enforces it uniformly across all 10, in both the live agent and the backtest.
TOP10_MIN_ENTRY_ENABLED = True
TOP10_MIN_ENTRY_TIME    = time(9, 30)

# ── #3 Regime gate: restrict strategy CLASS by the Nifty day-type ──
# Momentum strategies only on trend days (aligned with the trend direction),
# reversion strategies only on chop days; "trap" strategies always allowed.
# Before the decision time the regime is UNKNOWN and every strategy is allowed
# (many strategies legitimately fire in the 09:20-09:40 window, before an
# index day-type can be read).
# DISABLED after live-evidence review: on the 179 real live trades, the index was
# flat chop every day (Nifty moved <1% daily all month) so this gate read CHOP
# throughout and never engaged the actual stock-level bleed; 78% of signals also
# fire before the decision time (UNKNOWN = allowed). Kept in code, off by default.
TOP10_REGIME_GATE_ENABLED  = False
TOP10_REGIME_DECISION_TIME = time(9, 45)  # regime UNKNOWN (all allowed) before this
TOP10_REGIME_OR_BARS       = 3            # Nifty opening range = first 3 x 5-min bars (09:15-09:30)
TOP10_REGIME_ATR_BARS      = 12           # trailing bars for the range-expansion baseline
TOP10_REGIME_ATR_EXPANSION = 1.10         # current true range must exceed this x trailing avg to confirm a trend
# strategy -> class. MOMENTUM: favoured on trend days (direction-aligned).
# REVERSION: favoured on chop days. AGNOSTIC: the trapped-trader setups, always allowed.
TOP10_STRATEGY_CLASS = {
    "ORB-15":          "MOMENTUM",
    "SUPERTREND":      "MOMENTUM",
    "REL-STR":         "MOMENTUM",
    "INTRADAY-STRUCT": "MOMENTUM",
    "VWAP-REV":        "REVERSION",
    "RSI-EXT":         "REVERSION",
    "PIN-BAR":         "REVERSION",
    "VPOC":            "REVERSION",
    "FAILED-BO":       "AGNOSTIC",
    "FAILED-BD":       "AGNOSTIC",
}

# ── #4 Pullback entry: require a retest instead of chasing the extended bar ──
# After a signal fires, don't enter at the (often extended) signal bar. Wait
# for price to retrace a fraction of the entry->stop distance back toward the
# stop (a pullback) within a few bars, and enter there — a better price and a
# tighter, better-located stop. If the pullback never comes, skip the trade
# (that's the anti-chasing benefit — no entry at the top of the move).
# DISABLED after live-evidence review: applied to the 179 real live trades it
# threw away ~half (no retest came) and the trades that DID retest had a worse
# win rate (26.7% vs 39%) — "wait for a pullback toward the stop" selects for
# setups that immediately went against you, which more often continue to the
# stop. Net worse than the time-stop alone. Kept in code, off by default.
TOP10_PULLBACK_ENABLED  = False
TOP10_PULLBACK_FRACTION = 0.33  # retrace >= this fraction of entry->stop back toward the stop
TOP10_PULLBACK_MAX_BARS = 6     # ...within this many bars after the signal bar, else skip

# ── #5 Mid-session time-stop: cut trades going nowhere ──
# If a position isn't at least +MIN_R "R" of favourable excursion by TIMESTOP_BARS
# bars after entry, flatten it — free the capital rather than drift to the 15:15
# square-off near breakeven. R = entry-to-stop distance. This is a capital-
# velocity / variance control, not itself an alpha source.
# DISABLED after the combined live review: the time-stop's apparent benefit
# (cutting the all-trades loss in half) was really the 09:15 opening-candle
# effect in disguise — it was killing the same bad early trades. Once entries
# are filtered to >= 09:30 (#6 above), the time-stop HURTS (-Rs 15k -> -Rs 31k
# on the filtered set) because it cuts trades that would have recovered. The
# entry-time filter is the cleaner substitute. Kept in code, off by default.
TOP10_TIMESTOP_ENABLED = False
TOP10_TIMESTOP_BARS    = 12    # bars after entry to evaluate (12 x 5-min = 60 min)
TOP10_TIMESTOP_MIN_R   = 0.5   # flatten if favourable excursion < this many R by then

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

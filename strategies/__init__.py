from strategies.breakout.orb import ORB15, ORB30
from strategies.breakout.pdh_pdl import PDH_PDL
from strategies.breakout.gap_continuation import GapContinuation
from strategies.breakout.volume_spike import VolumeSpikeBreakout
from strategies.mean_reversion.vwap_reversion import VWAPReversion
from strategies.mean_reversion.rsi_extremes import RSIExtremes
from strategies.mean_reversion.bollinger import BollingerReversion
from strategies.mean_reversion.gap_fade import GapFade
from strategies.trend.ema_crossover import EMACrossover
from strategies.trend.supertrend import Supertrend
from strategies.trend.macd import MACDCrossover
from strategies.price_action.sr_breakout import SRBreakout
from strategies.price_action.nr7_inside import NR7InsideDay
from strategies.price_action.first_candle import FirstCandle
from strategies.pivot.cpr import CPR
from strategies.pivot.camarilla import Camarilla
from strategies.volatility.adx_filter import ADXFilter
from strategies.volatility.vwap_stddev import VWAPStdDev
from strategies.oscillator.stochastic import StochasticCrossover
from strategies.oscillator.volume_profile import VolumeProfile
from strategies.market_relative.relative_strength import RelativeStrength
from strategies.chart_patterns.double_bottom import DoubleBottom
from strategies.chart_patterns.falling_wedge import FallingWedge
from strategies.chart_patterns.ascending_triangle import AscendingTriangle
from strategies.chart_patterns.bull_flag import BullFlag
from strategies.multi_timeframe.daily_trend_bias import DailyTrendBias
# Phase 2B — bearish-only strategies
from strategies.bearish.double_top import DoubleTop
from strategies.bearish.desc_triangle import DescendingTriangle
from strategies.bearish.rise_wedge import RisingWedge
from strategies.bearish.bear_flag import BearFlag
from strategies.bearish.failed_breakout import FailedBreakout
from strategies.bearish.dead_cat import DeadCatBounce
from strategies.bearish.open_weakness import OpenWeakness
from strategies.bearish.bear_engulf import BearEngulfing
# Phase 2B — dual-direction strategies
from strategies.dual.pin_bar import PinBar
from strategies.dual.intraday_struct import IntradayStructure
# Phase 2B+ — bullish-only strategies (long-side mirrors of bearish ones)
from strategies.bullish.failed_breakdown import FailedBreakdown

ALL_STRATEGIES = [
    ORB15(), ORB30(), PDH_PDL(), GapContinuation(), VolumeSpikeBreakout(),
    VWAPReversion(), RSIExtremes(), BollingerReversion(), GapFade(),
    EMACrossover(), Supertrend(), MACDCrossover(),
    SRBreakout(), NR7InsideDay(), FirstCandle(),
    CPR(), Camarilla(),
    ADXFilter(), VWAPStdDev(),
    StochasticCrossover(), VolumeProfile(),
    RelativeStrength(),
    DoubleBottom(), FallingWedge(), AscendingTriangle(), BullFlag(),
    DailyTrendBias(),
    # Phase 2B
    DoubleTop(), DescendingTriangle(), RisingWedge(), BearFlag(),
    FailedBreakout(), DeadCatBounce(), OpenWeakness(), BearEngulfing(),
    PinBar(), IntradayStructure(),
    # Phase 2B+
    FailedBreakdown(),
]

STRATEGY_NAMES = [s.name for s in ALL_STRATEGIES]

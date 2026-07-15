"""Fixed 10-strategy roster for the Top-10 correlation-reduced backtest."""
from strategies.breakout.orb import ORB15
from strategies.bearish.failed_breakout import FailedBreakout
from strategies.bullish.failed_breakdown import FailedBreakdown
from strategies.mean_reversion.vwap_reversion import VWAPReversion
from strategies.mean_reversion.rsi_extremes import RSIExtremes
from strategies.trend.supertrend import Supertrend
from strategies.dual.pin_bar import PinBar
from strategies.dual.intraday_struct import IntradayStructure
from strategies.market_relative.relative_strength import RelativeStrength
from strategies.oscillator.volume_profile import VolumeProfile

TOP10_STRATEGIES = [
    ORB15(), FailedBreakout(), FailedBreakdown(), VWAPReversion(), RSIExtremes(),
    Supertrend(), PinBar(), IntradayStructure(), RelativeStrength(), VolumeProfile(),
]

TOP10_NAMES = [s.name for s in TOP10_STRATEGIES]

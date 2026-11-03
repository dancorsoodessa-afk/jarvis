"""JARVIS cryptocurrency market analysis package.

All crypto-specific connectors, indicators, risk calculations and desktop UI
are kept together in this package. Public data only; no order execution.
"""

from .analysis import TechnicalReport, analyze
from .market import MarketDataError, MarketSnapshot, PublicMarketClient
from .risk import TradePlan, build_plan

__all__ = [
    "MarketDataError", "MarketSnapshot", "PublicMarketClient",
    "TechnicalReport", "analyze", "TradePlan", "build_plan",
]

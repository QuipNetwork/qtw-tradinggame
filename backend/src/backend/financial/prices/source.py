"""Select the active market-data source from config.

Returns a process-wide singleton so the synthetic history/spot stay consistent
across the optimize pipeline and the MTM loop within a run.
"""

from __future__ import annotations

from ... import config
from .base import MarketDataSource
from .synthetic import SyntheticMarketSource

_source: MarketDataSource | None = None


def get_source() -> MarketDataSource:
    """Return the configured market-data source (cached)."""
    global _source
    if _source is None:
        _source = _build()
    return _source


def _build() -> MarketDataSource:
    name = config.MARKET_DATA_SOURCE
    if name == "synthetic":
        return SyntheticMarketSource()
    if name == "coingecko":
        raise NotImplementedError("CoinGecko source is pending")
    raise ValueError(f"unknown MARKET_DATA_SOURCE: {name!r}")


def set_source(source: MarketDataSource | None) -> None:
    """Override the active source (tests); pass None to reset to config default."""
    global _source
    _source = source

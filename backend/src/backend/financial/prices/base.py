"""Market-data source interface.

Everything downstream (estimators, pnl, job, scheduler) reads market data through
this protocol, so the assets-api client and the synthetic stand-in
are interchangeable — selected by ``config.MARKET_DATA_SOURCE`` with no pipeline
changes.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class MarketDataSource(Protocol):
    def hourly_returns(self, tickers: list[str], window_hours: int) -> np.ndarray:
        """Return a (T, N) matrix of hourly simple returns, T ≤ window_hours.

        Column i corresponds to ``tickers[i]``. r_{i,t} = P_{i,t} / P_{i,t-1} − 1
        between consecutive hours. Entries are NaN where an asset had no data
        that hour (closed hours, pre-listing) — gaps are never fabricated.
        """
        ...

    def spot_prices(self, tickers: list[str]) -> dict[str, float]:
        """Return the current USD spot price for each ticker."""
        ...

"""Hourly OHLCV history cache — pending.

Fetches and caches hourly close prices for the basket from CoinGecko, then
derives the simple-returns matrix the estimators consume. Aggressive caching is
required: CoinGecko's free tier allows only ~10–30 calls/min, and Σ needs
15 tickers × 720 hourly observations.
"""

from __future__ import annotations

import numpy as np


def fetch_hourly_returns(tickers: list[str], window_hours: int) -> np.ndarray:
    """Return an (T, N) matrix of hourly simple returns for ``tickers``.

    T = window_hours, N = len(tickers). r_{i,t} = P_{i,t} / P_{i,t-1} − 1.
    """
    raise NotImplementedError("prices.history.fetch_hourly_returns is pending")

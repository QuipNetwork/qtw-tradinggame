"""Live spot-price oracle — pending.

Provides current spot prices for mark-to-market revaluation and for sizing the
trade list on a retune. Distinct from history.py, which serves the cached
hourly window used by the estimators.
"""

from __future__ import annotations


def get_spot_prices(tickers: list[str]) -> dict[str, float]:
    """Return current USD spot price per ticker."""
    raise NotImplementedError("prices.oracle.get_spot_prices is pending")

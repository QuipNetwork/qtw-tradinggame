"""MarketDataSource backed by the assets-api service.

assets-api (gitlab.com/quip.network/assets-api) polls upstream providers
(Alpaca / Massive / CoinGecko) into SQLite and serves hourly OHLCV bars and
spot prices over REST; its response shapes are contractual with this protocol.

Bars are placed on a dense hourly grid and returns are taken between
*consecutive* hours, with **no fabrication**: a closed hour or not-yet-listed
hour stays missing (NaN), so a stock's overnight/weekend jump (close→next open)
is excluded — no single grid step spans it — and the estimators see only real
~1h returns. The covariance estimator handles the resulting NaN gaps.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import numpy as np

from ... import config


class AssetsApiError(RuntimeError):
    pass


class AssetsApiSource:
    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=(base_url or config.ASSETS_API_BASE_URL).rstrip("/"),
            timeout=config.ASSETS_API_TIMEOUT_S,
        )

    def _get(self, path: str, params: dict) -> dict:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise AssetsApiError(f"assets-api request failed: {path}: {e}") from e
        return response.json()

    def hourly_returns(self, tickers: list[str], window_hours: int) -> np.ndarray:
        # window_hours returns need window_hours + 1 price points; service caps at 90d.
        hours = min(2160, window_hours + 1)
        body = self._get("/v1/history", {"tickers": ",".join(tickers), "hours": hours})
        bars: dict[str, list[dict]] = body.get("bars", {})

        missing = [t for t in tickers if not bars.get(t)]
        if missing:
            raise AssetsApiError(f"no price history for: {missing}")

        # Dense hourly grid spanning all bars (basket-independent), so a stock's
        # closed-hours/weekend gap stays missing instead of collapsing into one
        # cross-session step — overnight jumps never become a 1h return.
        times = sorted({_parse_ts(bar["t"]) for series in bars.values() for bar in series})
        row = {t: i for i, t in enumerate(_hourly_grid(times[0], times[-1]))}
        prices = np.full((len(row), len(tickers)), np.nan)
        for col, ticker in enumerate(tickers):
            for bar in bars[ticker]:
                idx = row.get(_parse_ts(bar["t"]))
                if idx is not None:
                    prices[idx, col] = bar["c"]

        # Returns between consecutive grid hours; a NaN endpoint propagates to
        # NaN, leaving closed hours and pre-listing history absent, not faked.
        with np.errstate(invalid="ignore"):
            returns = prices[1:] / prices[:-1] - 1.0
        return returns[-window_hours:]

    def health(self) -> dict:
        return self._get("/healthz", {})

    def spot_prices(self, tickers: list[str]) -> dict[str, float]:
        body = self._get("/v1/spot", {"tickers": ",".join(tickers)})
        quotes: dict[str, dict] = body.get("prices", {})
        missing = [t for t in tickers if t not in quotes]
        if missing:
            raise AssetsApiError(f"no spot price for: {missing}")
        return {t: float(quotes[t]["price"]) for t in tickers}


def _parse_ts(ts: str) -> datetime:
    """Parse an RFC3339 UTC timestamp (e.g. '2026-06-15T17:00:00Z')."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _hourly_grid(start: datetime, end: datetime) -> list[datetime]:
    """Every hour in [start, end] inclusive — the dense grid bars are placed on."""
    grid, t = [], start
    while t <= end:
        grid.append(t)
        t += timedelta(hours=1)
    return grid

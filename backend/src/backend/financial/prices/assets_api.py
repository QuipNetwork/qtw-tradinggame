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

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np

from ... import config
from .base import SpotSnapshot


class AssetsApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class _CachedSpot:
    price: float
    as_of: str | None


class AssetsApiSource:
    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self._base_url = (base_url or config.ASSETS_API_BASE_URL).rstrip("/")
        self._owns_client = client is None
        self._client = client or self._new_client()
        self._spot_cache: dict[str, _CachedSpot] = {}

    def _new_client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=config.ASSETS_API_TIMEOUT_S)

    def _reset_client(self) -> None:
        if not self._owns_client:
            return
        try:
            self._client.close()
        finally:
            self._client = self._new_client()

    def _get(self, path: str, params: dict, *, retries: int | None = None) -> dict:
        attempts = (retries if retries is not None else config.ASSETS_API_RETRIES) + 1
        last_error: httpx.HTTPError | None = None
        for attempt in range(attempts):
            try:
                response = self._client.get(path, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.TransportError as e:
                last_error = e
                self._reset_client()
                if attempt < attempts - 1:
                    time.sleep(config.ASSETS_API_RETRY_BACKOFF_S * (attempt + 1))
                    continue
                break
            except httpx.HTTPStatusError as e:
                raise AssetsApiError(f"assets-api request failed: {path}: {e}") from e
        assert last_error is not None
        raise AssetsApiError(f"assets-api request failed: {path}: {last_error}") from last_error

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
                if idx is None:
                    continue
                # Coerce and keep only finite, positive closes. A bad payload
                # (0, null, string) would otherwise yield inf/−1 returns that
                # poison μ/Σ; leave it missing for the NaN-aware path instead.
                try:
                    close = float(bar["c"])
                except (TypeError, ValueError):
                    close = float("nan")
                if np.isfinite(close) and close > 0.0:
                    prices[idx, col] = close

        # Returns between consecutive grid hours; a NaN endpoint propagates to
        # NaN, leaving closed hours and pre-listing history absent, not faked.
        with np.errstate(invalid="ignore"):
            returns = prices[1:] / prices[:-1] - 1.0
        return returns[-window_hours:]

    def health(self) -> dict:
        return self._get("/healthz", {})

    def spot_prices(self, tickers: list[str]) -> dict[str, float]:
        prices, _ = self._fetch_spot(tickers)
        return prices

    def spot_snapshot(self, tickers: list[str]) -> SpotSnapshot:
        try:
            prices, as_of = self._fetch_spot(tickers)
            return SpotSnapshot(prices=prices, as_of=as_of, stale=False)
        except AssetsApiError:
            missing = [t for t in tickers if t not in self._spot_cache]
            if missing:
                raise
            cached = {t: self._spot_cache[t].price for t in tickers}
            as_of_values = [c.as_of for c in self._spot_cache.values() if c.as_of]
            return SpotSnapshot(
                prices=cached, as_of=min(as_of_values) if as_of_values else None, stale=True
            )

    def _fetch_spot(self, tickers: list[str]) -> tuple[dict[str, float], str | None]:
        body = self._get("/v1/spot", {"tickers": ",".join(tickers)})
        quotes: dict[str, dict] = body.get("prices", {})
        missing = [t for t in tickers if t not in quotes]
        if missing:
            raise AssetsApiError(f"no spot price for: {missing}")
        as_of = body.get("as_of") or datetime.now(UTC).isoformat()
        prices = {t: float(quotes[t]["price"]) for t in tickers}
        for ticker, price in prices.items():
            self._spot_cache[ticker] = _CachedSpot(
                price=price,
                as_of=quotes[ticker].get("t") or as_of,
            )
        return prices, as_of


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

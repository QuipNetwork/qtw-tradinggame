"""assets-api client: grid alignment, no-fabrication gaps, spot, error paths."""

from __future__ import annotations

import httpx
import numpy as np
import pytest

from backend.financial.prices.assets_api import AssetsApiError, AssetsApiSource


def _source(handler) -> AssetsApiSource:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return AssetsApiSource(client=client)


def _bar(t: str, c: float) -> dict:
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": 1.0}


def test_stock_gaps_stay_nan_and_overnight_jump_is_excluded():
    hours = [f"2026-06-05T{h:02d}:00:00Z" for h in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/history"
        return httpx.Response(
            200,
            json={
                "interval": "1h",
                "bars": {
                    # crypto: every hour, +1% per hour
                    "BTC": [_bar(t, 100.0 * 1.01**i) for i, t in enumerate(hours)],
                    # stock: trades hour 0, then closed hours 1-2, reopens 3-4
                    "IONQ": [_bar(hours[0], 50.0), _bar(hours[3], 52.0), _bar(hours[4], 51.0)],
                },
            },
        )

    returns = _source(handler).hourly_returns(["BTC", "IONQ"], window_hours=4)
    assert returns.shape == (4, 2)
    assert np.allclose(returns[:, 0], 0.01)
    # Closed hours are NaN (never zero-filled), and the 50→52 reopen move is
    # NOT a return — it would need the missing hour-2 price — so only the real
    # intraday 52→51 step survives. No fabrication, no overnight jump.
    col = returns[:, 1]
    assert np.isnan(col[:3]).all()
    assert col[3] == pytest.approx(51.0 / 52.0 - 1.0)


def test_missing_history_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": {"BTC": [_bar("2026-06-05T00:00:00Z", 1.0)]}})

    with pytest.raises(AssetsApiError, match="HON"):
        _source(handler).hourly_returns(["BTC", "HON"], window_hours=2)


def test_spot_prices():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/spot"
        return httpx.Response(
            200,
            json={
                "as_of": "2026-06-05T10:00:00Z",
                "prices": {
                    "BTC": {"price": 65180.4, "t": "2026-06-05T10:00:00Z", "stale": False},
                    "IONQ": {"price": 36.2, "t": "2026-06-05T09:59:00Z", "stale": True},
                },
            },
        )

    spot = _source(handler).spot_prices(["BTC", "IONQ"])
    assert spot == {"BTC": 65180.4, "IONQ": 36.2}


def test_http_error_wraps_into_assets_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(AssetsApiError, match="request failed"):
        _source(handler).spot_prices(["BTC"])

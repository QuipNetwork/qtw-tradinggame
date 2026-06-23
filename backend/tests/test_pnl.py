"""pnl.mark_to_market: holdings × spot → rolled-up AgentUpdate."""

from __future__ import annotations

import pytest

from backend.financial.pnl import mark_to_market


def test_flat_when_value_equals_bankroll():
    # 0.1 BTC @ 50k + 1 ETH @ 5k = 10_000 = bankroll → zero P&L.
    update = mark_to_market({"BTC": 0.1, "ETH": 1.0}, {"BTC": 50_000.0, "ETH": 5_000.0}, 10_000.0)
    assert update.total == pytest.approx(10_000.0)
    assert update.pl_usd == pytest.approx(0.0)
    assert update.pl_pct == pytest.approx(0.0)
    assert [h.ticker for h in update.holdings] == ["BTC", "ETH"]
    assert update.holdings[0].usd == pytest.approx(5_000.0)
    assert update.holdings[0].pct == pytest.approx(50.0)


def test_gain_is_reported_in_usd_and_pct():
    # BTC up 20% → holding worth 6_000, total 11_000 on a 10_000 bankroll.
    update = mark_to_market({"BTC": 0.1, "ETH": 1.0}, {"BTC": 60_000.0, "ETH": 5_000.0}, 10_000.0)
    assert update.total == pytest.approx(11_000.0)
    assert update.pl_usd == pytest.approx(1_000.0)
    assert update.pl_pct == pytest.approx(10.0)
    assert [h.ticker for h in update.holdings] == ["BTC", "ETH"]
    assert update.holdings[0].spot == pytest.approx(60_000.0)
    assert update.holdings[0].pct == pytest.approx(6_000.0 / 11_000.0 * 100.0)


def test_stale_snapshot_metadata_is_reported():
    update = mark_to_market(
        {"BTC": 0.1},
        {"BTC": 50_000.0},
        10_000.0,
        as_of="2026-06-17T12:00:00+00:00",
        stale=True,
    )
    assert update.as_of == "2026-06-17T12:00:00+00:00"
    assert update.stale is True


def test_zero_total_and_zero_bankroll_do_not_divide_by_zero():
    # Both division sites are guarded on the live MTM path: a zero total (e.g. a 0 spot price) must
    # not blow up the holding pct, and a zero bankroll must not blow up pl_pct.
    zero_total = mark_to_market({"BTC": 1.0}, {"BTC": 0.0}, 10_000.0)
    assert zero_total.total == pytest.approx(0.0)
    assert zero_total.pl_usd == pytest.approx(-10_000.0)
    assert zero_total.holdings[0].pct == pytest.approx(0.0)  # guarded: usd/total with total=0

    zero_bankroll = mark_to_market({"BTC": 0.1}, {"BTC": 50_000.0}, 0.0)
    assert zero_bankroll.total == pytest.approx(5_000.0)
    assert zero_bankroll.pl_pct == pytest.approx(0.0)  # guarded: pl_usd/bankroll with bankroll=0

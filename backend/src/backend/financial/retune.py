"""Diff old → new weights into a trade list.

First-solve vs retune is the caller's concern: pass w_old = 0 on a first solve.
Retunes are value-neutral — holdings are liquidated and rebought at spot to
match w_new with nothing deducted. There is no transaction fee; trade-frequency
pressure is handled by rate limiting (manual retune per-user, scheduled retunes
via the rebalance cadence, QPU access via a global budget), not by cost.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Trade:
    ticker: str
    delta_pct: float  # signed weight change × 100 (positive = buy, negative = sell)
    delta_usd: float  # signed dollar amount to trade


@dataclass(frozen=True)
class RetuneResult:
    trades: list[Trade]
    one_way_turnover: float  # ½ Σ|Δw_i| — fraction of the portfolio that turns over
    new_holdings_usd: dict[str, float]  # per-asset post-trade holdings


def compute_retune(
    w_old: np.ndarray,
    w_new: np.ndarray,
    tickers: list[str],
    portfolio_value_usd: float,
    weight_tol: float = 1e-6,
) -> RetuneResult:
    """Compute the trades that move a portfolio from w_old to w_new."""
    deltas = w_new - w_old
    trades = [
        Trade(
            ticker=ticker,
            delta_pct=float(delta * 100.0),
            delta_usd=float(delta * portfolio_value_usd),
        )
        for ticker, delta in zip(tickers, deltas, strict=True)
        if abs(delta) > weight_tol
    ]
    new_holdings_usd = {
        ticker: float(weight * portfolio_value_usd)
        for ticker, weight in zip(tickers, w_new, strict=True)
        if weight > weight_tol
    }
    return RetuneResult(
        trades=trades,
        one_way_turnover=float(0.5 * np.abs(deltas).sum()),
        new_holdings_usd=new_holdings_usd,
    )

"""Diff old → new weights into a trade list, with the V1 turnover fee.

This is where first-solve vs retune is decided — invisibly to the solver, which
only ever sees a fresh problem:
  - First solve: caller passes ``w_old = 0`` (no existing holdings).
  - Retune:      caller passes the drifted current weight vector.

In V0 the explicit fee is disabled (``config.V0_TRANSACTION_FEE_ENABLED = False``),
so a retune is value-neutral — holdings are liquidated and rebought at spot to
match ``w_new`` with nothing deducted. V1 turns the fee on; see IMPLEMENTATION_NOTES
for why the fee and the QUBO turnover penalty must ship together.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config


@dataclass(frozen=True)
class Trade:
    ticker: str
    delta_pct: float  # signed weight change × 100 (positive = buy, negative = sell)
    delta_usd: float  # signed dollar amount to trade


@dataclass(frozen=True)
class RetuneResult:
    trades: list[Trade]
    one_way_turnover: float  # ½ Σ|Δw_i| — fraction of the portfolio that turns over
    fee_usd: float  # 0.0 in V0
    new_holdings_usd: dict[str, float]  # per-asset post-trade holdings


def compute_retune(
    w_old: np.ndarray,
    w_new: np.ndarray,
    tickers: list[str],
    portfolio_value_usd: float,
    weight_tol: float = 1e-6,
) -> RetuneResult:
    """Compute the trades that move a portfolio from ``w_old`` to ``w_new``.

    Args:
        w_old: current (drifted) weights; all zeros on a first solve.
        w_new: freshly solved target weights (sums to 1).
        tickers: asset labels aligned with the weight vectors.
        portfolio_value_usd: portfolio value immediately before the retune.
        weight_tol: weights/deltas with magnitude ≤ this are treated as zero.

    Returns:
        RetuneResult with the signed trade list, one-way turnover, fee, and the
        resulting per-asset holdings.
    """
    deltas = w_new - w_old
    one_way_turnover = float(0.5 * np.abs(deltas).sum())

    if config.V0_TRANSACTION_FEE_ENABLED:
        fee_usd = config.TRANSACTION_FEE_RATE * one_way_turnover * portfolio_value_usd
    else:
        fee_usd = 0.0

    trades = [
        Trade(
            ticker=ticker,
            delta_pct=float(delta * 100.0),
            delta_usd=float(delta * portfolio_value_usd),
        )
        for ticker, delta in zip(tickers, deltas, strict=True)
        if abs(delta) > weight_tol
    ]

    investable = portfolio_value_usd - fee_usd
    new_holdings_usd = {
        ticker: float(weight * investable)
        for ticker, weight in zip(tickers, w_new, strict=True)
        if weight > weight_tol
    }

    return RetuneResult(
        trades=trades,
        one_way_turnover=one_way_turnover,
        fee_usd=fee_usd,
        new_holdings_usd=new_holdings_usd,
    )

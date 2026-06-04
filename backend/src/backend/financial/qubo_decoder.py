"""Decode a QUBO bitstring back to portfolio weights and PortfolioEntry[].

The bitstring layout matches the encoder:
- positions 0..Nb-1: weight bits x_{i,k}, with i = pos // b, k = pos % b
- positions Nb..Nb+N-1: cardinality indicators y_i  (informational only — the
  weights are determined by the x bits, not by y)
"""

from __future__ import annotations

import numpy as np

from ..api.schemas import PortfolioEntry
from ..solvers.types import DecodeMeta


def decode_bitstring(bits: np.ndarray, meta: DecodeMeta) -> np.ndarray:
    """Return the weight vector w (shape (N,)) from a QUBO bitstring.

    Mirrors the encoder: w_i = w_min · y_i + coef · Σ_k 2^k x_{i,k}. The y
    indicator contributes the minimum position, so a selected asset (y_i = 1)
    carries at least w_min and an unselected one carries zero.
    """
    if bits.shape != (meta.n_total_bits,):
        raise ValueError(f"bitstring length {bits.shape[0]} != expected {meta.n_total_bits}")

    N = meta.n_assets
    b = meta.bits_per_asset
    coef = meta.weight_coef

    weights = np.zeros(N)
    for i in range(N):
        increment = 0.0
        for k in range(b):
            increment += coef * (2**k) * bits[i * b + k]
        weights[i] = meta.w_min * bits[meta.n_weight_bits + i] + increment
    return weights


def weights_to_portfolio(
    weights: np.ndarray,
    tickers: list[str],
    bankroll_usd: float,
) -> list[PortfolioEntry]:
    """Convert weights → PortfolioEntry list, sorted descending by pct.

    Filters out zero positions. The remaining entries should be exactly K, but
    the caller is responsible for verifying cardinality via the feasibility
    checker — this function is shape-agnostic.
    """
    entries = []
    for ticker, w in zip(tickers, weights, strict=True):
        if w <= 0.0:
            continue
        entries.append(
            PortfolioEntry(
                ticker=ticker,
                pct=float(w) * 100.0,
                usd=float(w) * bankroll_usd,
            )
        )
    entries.sort(key=lambda e: e.pct, reverse=True)
    return entries

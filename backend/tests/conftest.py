"""Shared test fixtures — synthetic μ, Σ, and MIQP problems.

The optimizer is opaque to ticker semantics (it only sees μ and Σ), so the math
core is fully testable on synthetic data with no market-data dependency.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.prices.source import set_source
from backend.financial.prices.synthetic import SyntheticMarketSource
from backend.financial.types import MIQPProblem
from backend.persistence.agents import get_agent_store
from backend.persistence.jobs import get_job_store


@pytest.fixture(autouse=True)
def isolated_state():
    """Reset the in-memory stores and pin a deterministic, fixed-clock market.

    A constant clock makes spot prices stationary, so pipeline math is fully
    reproducible (a retune is value-neutral). Tests that need moving prices use
    their own mutable-clock source.
    """
    get_agent_store().reset()
    get_job_store().reset()
    set_source(SyntheticMarketSource(clock=lambda: 1000.0))
    yield
    set_source(None)
    get_agent_store().reset()
    get_job_store().reset()


@pytest.fixture
def synthetic_miqp_3assets() -> MIQPProblem:
    """A small, well-conditioned 3-asset mean-variance MIQP, K=2."""
    mu = np.array([0.02, 0.01, 0.005])
    sigma = np.array(
        [
            [0.04, 0.01, 0.005],
            [0.01, 0.03, 0.002],
            [0.005, 0.002, 0.01],
        ]
    )
    return MIQPProblem(
        mu=mu,
        Sigma=sigma,
        gamma=2.0,
        lambda_t=0.0,
        w_ref=np.zeros(3),
        w_max=0.6,
        K=2,
        asset_tickers=["A", "B", "C"],
    )


@pytest.fixture
def synthetic_returns() -> np.ndarray:
    """Deterministic correlated hourly returns, shape (720, 4).

    A shared market factor plus per-asset idiosyncratic noise gives a positive,
    non-degenerate covariance structure.
    """
    rng = np.random.default_rng(42)
    n_obs, n_assets = 720, 4
    factor = rng.normal(0.0, 0.01, size=(n_obs, 1))
    idiosyncratic = rng.normal(0.0, 0.005, size=(n_obs, n_assets))
    return factor + idiosyncratic

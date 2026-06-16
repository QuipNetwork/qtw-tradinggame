"""estimators: NaN-aware μ/Σ over ragged real data, variance floor, PSD repair."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.estimators.covariance import _psd_floor, covariance
from backend.financial.estimators.expected_return import expected_return


def test_covariance_shape_and_symmetry(synthetic_returns):
    n_assets = synthetic_returns.shape[1]
    sigma = covariance(synthetic_returns)
    assert sigma.shape == (n_assets, n_assets)
    assert np.allclose(sigma, sigma.T)
    # Diagonal variances are strictly positive for non-degenerate returns.
    assert np.all(np.diag(sigma) > 0)


def test_covariance_rejects_too_few_observations():
    with pytest.raises(ValueError):
        covariance(np.zeros((1, 4)))


def test_covariance_is_always_psd_on_ragged_data():
    # A thin column (mostly NaN, low overlap) is exactly what breaks naive cov.
    rng = np.random.default_rng(0)
    returns = rng.standard_normal((120, 4)) * 0.01
    returns[:100, 3] = np.nan  # asset 3: only 20 real obs, scant overlap
    sigma = covariance(returns, ["crypto", "crypto", "stock", "stock"])
    assert np.allclose(sigma, sigma.T)
    np.linalg.cholesky(sigma)  # raises unless positive-definite


def test_covariance_floors_thin_asset_variance_to_its_class():
    rng = np.random.default_rng(1)
    returns = rng.standard_normal((100, 3)) * 0.01
    returns[:94, 2] = np.nan  # asset 2: 6 real obs (< MIN_RETURN_OBS) → floored
    sigma = covariance(returns, ["crypto", "stock", "stock"])
    # asset 1 is the only reliable stock, so the floor is its variance; asset 2's
    # 6-hour overlap is below MIN_COV_PAIRS, so its off-diagonals stay 0.
    assert sigma[2, 2] == pytest.approx(sigma[1, 1])


def test_covariance_zeros_low_overlap_pairs():
    # Two assets that never trade in the same hour → no overlap → cov 0.
    returns = np.full((100, 2), np.nan)
    rng = np.random.default_rng(2)
    returns[:50, 0] = rng.standard_normal(50) * 0.01
    returns[50:, 1] = rng.standard_normal(50) * 0.01
    sigma = covariance(returns, ["crypto", "crypto"])
    assert sigma[0, 1] == 0.0


def test_psd_floor_repairs_an_indefinite_matrix():
    # Pairwise overlaps can produce a non-PSD matrix; the floor must fix it.
    m = np.array([[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]])
    assert np.linalg.eigvalsh(m).min() < 0
    repaired = _psd_floor(m, 1e-4)
    assert np.allclose(repaired, repaired.T)
    np.linalg.cholesky(repaired)  # PSD now


def test_expected_return_uses_only_the_tau_window():
    # 10 hours: first 5 all +0.10, last 5 all -0.02, single asset.
    returns = np.array([[0.10]] * 5 + [[-0.02]] * 5)
    mu_short = expected_return(returns, tau_hours=5, min_obs=1)
    mu_full = expected_return(returns, tau_hours=10, min_obs=1)
    assert mu_short[0] == pytest.approx(-0.02)
    assert mu_full[0] == pytest.approx(0.04)


def test_expected_return_clamps_tau_to_available_history():
    returns = np.array([[0.01, 0.02]] * 3)
    mu = expected_return(returns, tau_hours=999, min_obs=1)
    assert mu == pytest.approx([0.01, 0.02])


def test_expected_return_ignores_nan_gaps():
    returns = np.full((60, 1), 0.02)
    returns[::2, 0] = np.nan  # 30 real obs, all 0.02
    mu = expected_return(returns, tau_hours=60)
    assert mu[0] == pytest.approx(0.02)


def test_expected_return_zeros_assets_below_min_obs():
    returns = np.full((50, 2), 0.01)
    returns[:45, 1] = np.nan  # asset 1: only 5 real obs (< MIN_RETURN_OBS)
    mu = expected_return(returns, tau_hours=50)
    assert mu[0] == pytest.approx(0.01)
    assert mu[1] == 0.0


def test_expected_return_rejects_nonpositive_tau(synthetic_returns):
    with pytest.raises(ValueError):
        expected_return(synthetic_returns, tau_hours=0)

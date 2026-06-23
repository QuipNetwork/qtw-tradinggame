"""Covariance estimator Σ from ragged, real-only returns.

Σ is built on the fixed 30-day window. Because we never fabricate returns,
assets carry unequal observation counts, so Σ is assembled from pairwise
overlaps:

  • diagonal var_i — from asset i's real returns; floored at the class-median
    variance when i has < MIN_RETURN_OBS observations, so a thin / just-listed
    asset can't read as artificially calm;
  • off-diagonal cov(i,j) — correlation estimated over the hours where both i and
    j are real (so it is a valid |ρ| ≤ 1), then rescaled by the per-asset vols;
    set to 0 below MIN_COV_PAIRS overlapping points.

Pairwise overlaps don't form a valid covariance on their own, so we (1) clip
implied correlations into range, (2) shrink toward the diagonal to damp noise,
then (3) floor eigenvalues so the matrix the solvers see is positive
semidefinite. Shrinkage alone does NOT guarantee PSD — diagonal shrinkage only
scales the off-diagonals, so an indefinite block can survive; the eigenvalue
floor is the guarantee.

This module is pure: it takes a returns matrix (NaN where data is missing) and
the per-asset classes used for the variance floor.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ... import config


def covariance(
    returns: np.ndarray,
    asset_classes: Sequence[str] | None = None,
    *,
    min_obs: int | None = None,
    min_pairs: int | None = None,
    shrinkage: float | None = None,
    max_abs_corr: float | None = None,
    eig_floor_rel: float | None = None,
) -> np.ndarray:
    """Robust covariance Σ (N, N) from an hourly returns matrix with gaps.

    Args:
        returns: shape (T, N) — T hourly observations across N assets, NaN where
            an asset had no data that hour.
        asset_classes: class label per column (e.g. "crypto"/"stock"), used to
            pick a variance floor for thin assets. None → all one class.

    Returns:
        Σ (N, N), symmetric and positive semidefinite.
    """
    if returns.ndim != 2:
        raise ValueError(f"returns must be 2-D (T, N), got shape {returns.shape}")
    if returns.shape[0] < 2:
        raise ValueError("need at least 2 observations for a sample covariance")

    min_obs = config.MIN_RETURN_OBS if min_obs is None else min_obs
    min_pairs = config.MIN_COV_PAIRS if min_pairs is None else min_pairs
    shrinkage = config.COV_SHRINKAGE if shrinkage is None else shrinkage
    max_abs_corr = config.COV_MAX_ABS_CORR if max_abs_corr is None else max_abs_corr
    eig_floor_rel = config.COV_EIG_FLOOR_REL if eig_floor_rel is None else eig_floor_rel

    _, n = returns.shape
    finite = np.isfinite(returns)
    counts = finite.sum(axis=0)
    var = _variances(returns, counts, asset_classes, min_obs)

    sigma = np.diag(var).astype(float)
    std = np.sqrt(var)
    for i in range(n):
        for j in range(i + 1, n):
            mask = finite[:, i] & finite[:, j]
            if int(mask.sum()) < min_pairs:
                continue  # too little overlap — leave the pair uncorrelated (0)
            # Estimate correlation on the SAME overlap sample (variances and
            # covariance share rows, so |ρ| ≤ 1 by construction), then rescale by
            # the trusted per-asset vol. Normalizing an overlap covariance by
            # full-window variances mixes samples and can imply |corr| > 1 — the
            # clip would mask that, not fix it.
            cov = np.cov(returns[mask, i], returns[mask, j], ddof=1)
            var_i_o, var_j_o, cov_ij = float(cov[0, 0]), float(cov[1, 1]), float(cov[0, 1])
            if var_i_o <= 0.0 or var_j_o <= 0.0:
                continue  # degenerate overlap variance — leave uncorrelated (0)
            rho = float(np.clip(cov_ij / np.sqrt(var_i_o * var_j_o), -max_abs_corr, max_abs_corr))
            sigma[i, j] = sigma[j, i] = rho * std[i] * std[j]

    sigma = (1.0 - shrinkage) * sigma + shrinkage * np.diag(np.diag(sigma))
    return _psd_floor(sigma, eig_floor_rel)


def _variances(
    returns: np.ndarray,
    counts: np.ndarray,
    asset_classes: Sequence[str] | None,
    min_obs: int,
) -> np.ndarray:
    """Per-asset variance from real returns; class-median floor when too thin."""
    n = returns.shape[1]
    raw = np.full(n, np.nan)
    for i in range(n):
        if counts[i] >= 2:
            raw[i] = np.nanvar(returns[:, i], ddof=1)
    reliable = (counts >= min_obs) & np.isfinite(raw) & (raw > 0)
    classes = [""] * n if asset_classes is None else list(asset_classes)

    var = raw.copy()
    for i in range(n):
        if not reliable[i]:
            var[i] = _class_floor(i, classes, raw, reliable)
    return var


def _class_floor(i: int, classes: Sequence[str], raw: np.ndarray, reliable: np.ndarray) -> float:
    """Median reliable variance of i's class, widening to all assets if needed."""
    same = [raw[j] for j in range(len(classes)) if reliable[j] and classes[j] == classes[i]]
    if same:
        return float(np.median(same))
    if reliable.any():
        return float(np.median(raw[reliable]))
    positive = raw[np.isfinite(raw) & (raw > 0)]
    return float(np.median(positive)) if positive.size else config.COV_DEFAULT_VAR


def _psd_floor(sigma: np.ndarray, eig_floor_rel: float) -> np.ndarray:
    """Floor eigenvalues at a small positive level so Σ is PSD (eigenvalue clip)."""
    floor = max(eig_floor_rel * float(np.mean(np.diag(sigma))), 1e-12)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    if eigvals.min() >= floor:
        return sigma
    repaired = (eigvecs * np.maximum(eigvals, floor)) @ eigvecs.T
    return (repaired + repaired.T) / 2.0  # re-symmetrize against round-off

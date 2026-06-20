"""Decoder: bit-grid round-trips, w_min offset, simplex normalization."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.qubo_decoder import decode_bitstring
from backend.solvers.types import DecodeMeta


@pytest.fixture
def meta() -> DecodeMeta:
    return DecodeMeta(
        n_assets=3, bits_per_asset=4, w_max=0.6, w_min=0.1, asset_tickers=["A", "B", "C"]
    )


def _bits_for_levels(levels: list[int], meta: DecodeMeta) -> np.ndarray:
    bits = np.zeros(meta.n_total_bits, dtype=np.int8)
    for i, level in enumerate(levels):
        for k in range(meta.bits_per_asset):
            bits[i * meta.bits_per_asset + k] = (level >> k) & 1
    return bits


def test_zero_bits_decode_to_w_min(meta):
    weights = decode_bitstring(np.zeros(meta.n_total_bits, dtype=np.int8), meta)
    assert np.allclose(weights, meta.w_min)


def test_all_bits_decode_to_w_max(meta):
    weights = decode_bitstring(np.ones(meta.n_total_bits, dtype=np.int8), meta)
    assert np.allclose(weights, meta.w_max)


def test_decode_matches_integer_levels(meta):
    levels = [5, 0, 15]
    weights = decode_bitstring(_bits_for_levels(levels, meta), meta)
    expected = [meta.w_min + level * meta.weight_coef for level in levels]
    assert weights == pytest.approx(expected)


def test_normalize_projects_near_budget_onto_simplex(meta):
    # levels chosen so the raw sum is close to but not exactly 1
    bits = _bits_for_levels([8, 8, 6], meta)
    raw = decode_bitstring(bits, meta)
    assert abs(raw.sum() - 1.0) > 1e-6

    normalized = decode_bitstring(bits, meta, normalize=True)
    assert normalized.sum() == pytest.approx(1.0)


def test_normalize_leaves_bad_sums_alone(meta):
    bits = np.ones(meta.n_total_bits, dtype=np.int8)  # sums to 1.8 — way off
    raw = decode_bitstring(bits, meta, normalize=True)
    assert raw.sum() == pytest.approx(1.8)


def test_wrong_length_bitstring_raises(meta):
    with pytest.raises(ValueError):
        decode_bitstring(np.zeros(meta.n_total_bits - 1, dtype=np.int8), meta)


# --- Method 3 (integer-units selection) decode ---


@pytest.fixture
def m3meta() -> DecodeMeta:
    # M=16, b=3, u_min=1 → held weights on {1/16 … 8/16}; layout [y_0..y_2, x bits].
    return DecodeMeta(
        n_assets=3,
        bits_per_asset=3,
        w_max=0.5,
        w_min=1 / 16,
        asset_tickers=["A", "B", "C"],
        scheme="method3",
        n_units_M=16,
        u_min_units=1,
        increment_bits=3,
    )


def _m3_bits(units: dict[int, int], meta: DecodeMeta) -> np.ndarray:
    bits = np.zeros(meta.n_total_bits, dtype=np.int8)
    for i, u in units.items():
        if u > 0:
            bits[meta.y(i)] = 1
            inc = u - meta.u_min_units
            for k in range(meta.increment_bits):
                bits[meta.x(i, k)] = (inc >> k) & 1
    return bits


def test_method3_unselected_decodes_to_zero(m3meta):
    # increment bits set, but the select bit is off → weight must be 0
    bits = np.zeros(m3meta.n_total_bits, dtype=np.int8)
    for k in range(m3meta.increment_bits):
        bits[m3meta.x(0, k)] = 1
    weights = decode_bitstring(bits, m3meta)
    assert weights[0] == 0.0


def test_method3_decode_is_exact_no_normalize(m3meta):
    # 8 + 4 + 4 = 16 = M → Σw = 1 exactly, with normalize=False (no crutch)
    weights = decode_bitstring(_m3_bits({0: 8, 1: 4, 2: 4}, m3meta), m3meta)
    assert weights == pytest.approx([8 / 16, 4 / 16, 4 / 16])
    assert weights.sum() == 1.0  # exact, not approx

"""QUBO bit discretization: decode is the exact inverse of the bit grid, and
projecting an arbitrary weight onto the grid round-trips within one quantum.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.qubo_decoder import decode_bitstring
from backend.solvers.types import DecodeMeta


def _weights_to_bitstring(weights: np.ndarray, meta: DecodeMeta) -> np.ndarray:
    """Project weights onto the nearest bit-grid levels → full QUBO bitstring."""
    b = meta.bits_per_asset
    coef = meta.weight_coef
    max_level = 2**b - 1
    bits = np.zeros(meta.n_total_bits, dtype=np.int8)
    for i, w in enumerate(weights):
        level = min(max_level, max(0, int(round(w / coef))))
        for k in range(b):
            bits[i * b + k] = (level >> k) & 1
        if level > 0:
            bits[meta.n_weight_bits + i] = 1  # cardinality indicator
    return bits


@pytest.fixture
def meta() -> DecodeMeta:
    return DecodeMeta(n_assets=3, bits_per_asset=4, w_max=0.6, asset_tickers=["A", "B", "C"])


def test_all_bits_set_decodes_to_w_max(meta: DecodeMeta):
    bits = np.zeros(meta.n_total_bits, dtype=np.int8)
    bits[: meta.bits_per_asset] = 1  # asset 0: levels 0b1111 = 15
    weights = decode_bitstring(bits, meta)
    assert weights[0] == pytest.approx(meta.w_max)
    assert weights[1] == 0.0
    assert weights[2] == 0.0


def test_decode_matches_integer_levels(meta: DecodeMeta):
    # Asset 1 at level 0b0101 = 5 → weight = coef * 5.
    bits = np.zeros(meta.n_total_bits, dtype=np.int8)
    bits[meta.bits_per_asset + 0] = 1  # bit k=0 (value 1)
    bits[meta.bits_per_asset + 2] = 1  # bit k=2 (value 4)
    weights = decode_bitstring(bits, meta)
    assert weights[1] == pytest.approx(meta.weight_coef * 5)


def test_roundtrip_within_one_quantum(meta: DecodeMeta):
    coef = meta.weight_coef
    rng = np.random.default_rng(0)
    for _ in range(50):
        w = rng.uniform(0.0, meta.w_max, size=meta.n_assets)
        decoded = decode_bitstring(_weights_to_bitstring(w, meta), meta)
        assert np.all(np.abs(decoded - w) <= coef / 2 + 1e-9)


def test_wrong_length_bitstring_raises(meta: DecodeMeta):
    with pytest.raises(ValueError):
        decode_bitstring(np.zeros(meta.n_total_bits - 1, dtype=np.int8), meta)


def test_min_position_offset_from_y_indicator():
    # bits span [w_min, w_max]; the y indicator adds the minimum position.
    meta = DecodeMeta(n_assets=2, bits_per_asset=4, w_max=0.6, w_min=0.1, asset_tickers=["A", "B"])
    bits = np.zeros(meta.n_total_bits, dtype=np.int8)
    bits[: meta.bits_per_asset] = 1  # asset 0: all weight bits → top of span
    bits[meta.n_weight_bits + 0] = 1  # asset 0 selected (y_0 = 1) → w_max
    bits[meta.n_weight_bits + 1] = 1  # asset 1 selected, no bits → exactly w_min
    weights = decode_bitstring(bits, meta)
    assert weights[0] == pytest.approx(0.6)
    assert weights[1] == pytest.approx(0.1)

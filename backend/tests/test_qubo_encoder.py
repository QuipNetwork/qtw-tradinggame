"""qubo_encoder: matrix shape, symmetry, and a stable hash."""

from __future__ import annotations

import numpy as np

from backend import config
from backend.financial.qubo_encoder import encode_qubo, qubo_hash


def test_shape_and_symmetry(synthetic_miqp_3assets):
    qubo = encode_qubo(synthetic_miqp_3assets)
    n = synthetic_miqp_3assets.N
    b = config.BIT_PRECISION
    # N·b weight bits + N cardinality indicators = N·(b+1).
    expected = n * (b + 1)
    assert qubo.Q.shape == (expected, expected)
    assert np.allclose(qubo.Q, qubo.Q.T)


def test_hash_is_stable_and_content_addressed(synthetic_miqp_3assets):
    first = qubo_hash(encode_qubo(synthetic_miqp_3assets))
    second = qubo_hash(encode_qubo(synthetic_miqp_3assets))
    assert first == second
    assert len(first) == 64  # SHA-256 hex digest


def test_higher_bit_precision_grows_the_matrix(synthetic_miqp_3assets):
    n = synthetic_miqp_3assets.N
    q4 = encode_qubo(synthetic_miqp_3assets, bits_per_asset=4)
    q5 = encode_qubo(synthetic_miqp_3assets, bits_per_asset=5)
    assert q4.Q.shape == (n * 5, n * 5)
    assert q5.Q.shape == (n * 6, n * 6)

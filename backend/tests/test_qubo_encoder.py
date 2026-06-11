"""QUBO encoder: shape, symmetry, hashing."""

from __future__ import annotations

import numpy as np

from backend.financial.qubo_encoder import encode_qubo, qubo_hash


def test_shape_and_symmetry(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets, bits_per_asset=4)
    assert qubo.Q.shape == (12, 12)  # N=3 × b=4, no indicator block
    assert np.allclose(qubo.Q, qubo.Q.T)


def test_hash_is_stable_and_content_addressed(synthetic_problem_3assets):
    a = encode_qubo(synthetic_problem_3assets)
    b = encode_qubo(synthetic_problem_3assets)
    assert qubo_hash(a) == qubo_hash(b)

    synthetic_problem_3assets.gamma = 5.0
    c = encode_qubo(synthetic_problem_3assets)
    assert qubo_hash(a) != qubo_hash(c)


def test_higher_bit_precision_grows_the_matrix(synthetic_problem_3assets):
    q4 = encode_qubo(synthetic_problem_3assets, bits_per_asset=4)
    q5 = encode_qubo(synthetic_problem_3assets, bits_per_asset=5)
    assert q5.n == q4.n + 3  # one extra bit per asset

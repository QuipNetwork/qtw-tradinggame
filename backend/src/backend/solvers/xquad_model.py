"""Convert the portfolio's floating-point QUBO to xquad's integer XQMX."""

from __future__ import annotations

import math

from .types import QuboMatrix


def to_xqmx(qubo: QuboMatrix):
    """Return (model, scale), bounding Ising biases after binary-to-spin conversion.

    xquad 0.4.0 uses integer coefficients; the Quip codec multiplies spin
    biases by 1000 and stores them as i32. A per-instance scale retains useful
    QUBO precision without overflowing a dense model's incident field sums.
    """
    from xqvm_py.xqmx import XQMX

    terms = qubo.to_dict()
    if not all(math.isfinite(value) for value in terms.values()):
        raise ValueError("QUBO coefficients must be finite")
    incident = [0.0] * qubo.n
    for (i, j), value in terms.items():
        incident[i] += abs(value)
        if j != i:
            incident[j] += abs(value)
    peak = max(incident, default=0.0)
    if peak == 0:
        raise ValueError("QUBO has no nonzero coefficients")
    # Leave generous room for rounding and the binary->spin transform.
    scale = min(1_000_000_000.0, 1_000.0 / peak)
    model = XQMX.binary_model(qubo.n)
    retained = 0
    for (i, j), coefficient in terms.items():
        rounded = round(coefficient * scale)
        if rounded == 0:
            continue
        retained += 1
        if i == j:
            model.set_linear(i, rounded)
        else:
            model.set_quadratic(i, j, rounded)
    if retained == 0:
        raise ValueError("QUBO coefficients vanish at xquad integer precision")
    return model, scale


def smoke_xqmx():
    """Return a two-variable model for an end-to-end Quip connectivity check.

    Its coupling graph is one edge, so it tests RPC, H4 signing, submission,
    mining, and result decoding without requiring a minor embedding.
    """
    from xqvm_py.xqmx import XQMX

    model = XQMX.spin_model(2)
    model.set_quadratic(0, 1, 1)
    return model

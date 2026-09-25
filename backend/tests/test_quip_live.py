"""Live end-to-end check against the Quip testnet (Aglais): signup → optimize → chain read-back.

Opt-in, because each run proposes one on-chain order (about 1 AGLS reward plus fee):

    QTW_QUIP_LIVE=1 QUIP_KEYSTORE=~/.quip/keystore.json uv run pytest -q -s tests/test_quip_live.py

The test drives the real FastAPI app over HTTP with XQUAD_BACKEND=quip, then reads the order
the race reported back from the chain with a separate SolverQuip client, so the proof does not
rest on the adapter's own view of the result.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import create_app
from backend.solvers.providers import xquad

pytestmark = pytest.mark.skipif(
    os.environ.get("QTW_QUIP_LIVE") != "1"
    or not (os.environ.get("QUIP_KEYSTORE") or os.environ.get("QUIP_SIGNER_SEED")),
    reason="live Quip test: set QTW_QUIP_LIVE=1 and QUIP_KEYSTORE or QUIP_SIGNER_SEED",
)

# The full 28-asset universe: its select-encoding QUBO couples every asset to every other,
# which no registered hardware topology can host.
_UNIVERSE = [
    "BTC", "ETH", "SOL", "USDC", "USDT", "BNB", "XRP", "DOGE", "HYPE", "ZEC",
    "ALGO", "FIL", "RENDER", "STRK", "IONQ", "QBTS", "RGTI", "QUBT", "ARQQ", "LAES",
    "IBM", "GOOGL", "NVDA", "MSFT", "AMZN", "HON", "SAF", "SPCX",
]  # fmt: skip
_HOLD = 8


def test_optimize_solves_the_portfolio_on_the_quip_testnet(monkeypatch):
    monkeypatch.setenv("XQUAD_BACKEND", "quip")
    submitted = []
    real_to_xqmx = xquad.to_xqmx

    def recording_to_xqmx(qubo):
        model, scale = real_to_xqmx(qubo)
        submitted.append(model)
        return model, scale

    monkeypatch.setattr(xquad, "to_xqmx", recording_to_xqmx)

    with TestClient(create_app()) as client:
        signup = client.post(
            "/agents",
            json={
                "name": "Quip Live Check",
                "email": "quip-live@example.com",
                "sliders": {
                    "rebalanceFrequency": 50,
                    "riskPreference": 50,
                    "maxPositionSize": 50,
                    "holdCount": _HOLD,
                },
                "assets": _UNIVERSE,
            },
        )
        assert signup.status_code == 200, signup.text
        agent = signup.json()
        response = client.post(
            f"/agents/{agent['agentId']}/optimize",
            headers={"Authorization": f"Bearer {agent['token']}"},
        )
    assert response.status_code == 200, response.text
    result = response.json()

    runs = {run["provider"]: run for run in result["solverResults"]}
    print("\nsolver results:")
    for run in result["solverResults"]:
        print(
            f"  {run['provider']:<24} {run['providerType']:<8} {run['status']:<9} "
            f"solve={run['solveTime']} objective={run['objective']} order={run.get('orderId')}"
        )

    quip = runs["Quip testnet (xquad)"]
    assert quip["providerType"] == "NETWORK"
    assert quip["status"] in ("winner", "feasible"), quip
    assert quip["feasible"] is True
    assert quip["orderId"] is not None

    held = [entry for entry in result["portfolio"] if entry["pct"] > 0]
    assert len(held) == _HOLD
    assert sum(entry["pct"] for entry in result["portfolio"]) == pytest.approx(100, abs=1e-3)

    # Independent read-back: a fresh client re-derives the order from chain state.
    from xqsa import SolverQuip

    assert len(submitted) == 1
    model = submitted[0]
    assert model.size == len(_UNIVERSE)
    reader = SolverQuip(url=config.QUIP_RPC_URL, faucet=config.QUIP_FAUCET_URL)
    onchain = reader.query(int(quip["orderId"]), model, topology="native")
    assert onchain is not None, "order is not final on chain"
    print(
        f"chain read-back: order={onchain.metadata['order_id']} energy={onchain.energy} "
        f"energy_matches_chain={onchain.metadata['energy_matches_chain']} "
        f"submissions={onchain.metadata['num_submissions']} "
        f"miner={onchain.metadata.get('solver')}"
    )
    assert onchain.metadata["energy_matches_chain"] is True
    assert onchain.metadata["num_submissions"] >= 1

"""API request-schema input bounds — oversized payloads are rejected at the boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.api.schemas import AgentConfig, OptimizeRequest, SliderValues


def _sliders(**kw) -> SliderValues:
    base = {"rebalanceFrequency": 50, "riskPreference": 50, "maxPositionSize": 50}
    base.update(kw)
    return SliderValues(**base)


def test_holdcount_bounds():
    _sliders(holdCount=28)  # ok
    with pytest.raises(ValidationError):
        _sliders(holdCount=101)  # above le
    with pytest.raises(ValidationError):
        _sliders(holdCount=2)  # below ge=3


def test_agent_config_string_and_list_bounds():
    AgentConfig(name="Quanta", sliders=_sliders(), assets=["BTC", "ETH"])  # ok
    with pytest.raises(ValidationError):
        AgentConfig(name="x" * 81, sliders=_sliders())  # name too long
    with pytest.raises(ValidationError):
        AgentConfig(name="ok", email="x" * 255, sliders=_sliders())  # email too long
    with pytest.raises(ValidationError):
        AgentConfig(name="ok", sliders=_sliders(), assets=["BTC"] * 65)  # too many assets
    with pytest.raises(ValidationError):
        AgentConfig(name="ok", sliders=_sliders(), assets=["A" * 13])  # ticker item too long


def test_optimize_request_assets_bounds():
    OptimizeRequest(assets=["BTC", "ETH"])  # ok
    OptimizeRequest()  # ok (assets optional)
    with pytest.raises(ValidationError):
        OptimizeRequest(assets=["BTC"] * 65)  # too many
    with pytest.raises(ValidationError):
        OptimizeRequest(assets=["A" * 13])  # item too long

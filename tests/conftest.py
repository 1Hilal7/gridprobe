"""Shared real scenario fixtures for tests of the CASE-002 measurements."""

from pathlib import Path

import pytest

from backend.scenarios.loader import load_scenario
from backend.scenarios.models import ScenarioCase


@pytest.fixture
def phase_imbalance_scenario_path() -> Path:
    return Path(__file__).resolve().parents[1] / "demo/scenarios/case_002_phase_imbalance.json"


@pytest.fixture
def phase_imbalance_case(phase_imbalance_scenario_path: Path) -> ScenarioCase:
    """Load a fresh case per test, preserving isolation when test data is mutated."""
    return load_scenario(phase_imbalance_scenario_path)

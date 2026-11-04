"""Load deterministic JSON cases for internal scenario/evaluation use only.

ValidationError is propagated for malformed JSON or invalid case data;
filesystem errors are propagated to the caller. No data is generated or fixed.
"""

from pathlib import Path

from backend.scenarios.models import ScenarioCase


DEFAULT_SCENARIO_DIRECTORY = Path(__file__).resolve().parents[2] / "demo" / "scenarios"


def load_scenario(path: str | Path) -> ScenarioCase:
    """Read and validate one UTF-8 JSON case, including evaluation annotations."""
    return ScenarioCase.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_scenarios(
    directory: str | Path = DEFAULT_SCENARIO_DIRECTORY,
) -> list[ScenarioCase]:
    """Load top-level *.json cases in filename order, independent of cwd.

    An existing empty directory returns an empty list. Missing directories and
    invalid cases fail explicitly instead of silently skipping data.
    """
    scenario_directory = Path(directory)
    if not scenario_directory.is_dir():
        if not scenario_directory.exists():
            raise FileNotFoundError(scenario_directory)
        raise NotADirectoryError(scenario_directory)
    return [load_scenario(path) for path in sorted(scenario_directory.glob("*.json"))]

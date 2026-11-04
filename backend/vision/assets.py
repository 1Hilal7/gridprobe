"""Resolve only scenario-owned assets, never model-supplied filesystem paths."""

from pathlib import Path

from backend.vision.errors import SamImageError, SamPathError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = REPOSITORY_ROOT / "demo/assets"


def resolve_scenario_image(reference: str) -> Path:
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts or "\\" in reference or "\x00" in reference:
        raise SamPathError("The scenario image path is outside the demo asset area.")
    try:
        path = (REPOSITORY_ROOT / relative).resolve()
        # Compare with the lexical asset root: an assets symlink must not escape.
        if not path.is_relative_to(ASSET_ROOT) or path == ASSET_ROOT:
            raise SamPathError("The scenario image path is outside the demo asset area.")
        if not path.is_file():
            raise SamImageError("The scenario image asset is missing or unavailable.")
        return path
    except OSError:
        raise SamImageError("The scenario image asset is missing or unavailable.") from None
    except (ValueError, RuntimeError):
        raise SamPathError("The scenario image path cannot be resolved inside the demo asset area.") from None

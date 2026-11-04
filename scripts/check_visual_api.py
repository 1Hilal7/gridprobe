"""Opt-in real Muse image-observation check; no diagnostic output."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from backend.vision.errors import SamError
from backend.vision.observation_errors import VisualObservationError
from backend.vision.observation_provider import MuseVisualProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Describe visible component properties with Muse Spark.")
    parser.add_argument("image", type=Path)
    parser.add_argument("component", help="Short component noun phrase")
    args = parser.parse_args(argv)
    try:
        result = MuseVisualProvider().observe(args.image, args.component)
    except (SamError, VisualObservationError) as error:
        print(f"Visual observation check failed ({error.code}). Check the image, configuration, and provider.")
        return 1
    except ValidationError:
        print("Provide a short component noun phrase without condition claims.")
        return 2
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Opt-in real SAM connectivity check; never imported as an automated test."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from backend.vision.errors import SamError
from backend.vision.provider import SamProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real SAM 3.1 component segmentation.")
    parser.add_argument("image", type=Path)
    parser.add_argument("concept", help="Short component noun phrase, e.g. electrical terminal")
    args = parser.parse_args(argv)
    try:
        result = SamProvider().segment(args.image, args.concept)
    except SamError as error:
        # Messages are authored here, never copied from SDK/API exceptions.
        print(json.dumps({"status": "error", "code": error.code,
                          "message": "SAM check failed. Check the image, server credential, and provider availability."}))
        return 1
    except ValidationError:
        print("Use a short, concrete component noun phrase.")
        return 2
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit live evaluation: python -m scripts.run_evaluation.

No network requests occur on import or --help. Reports are written only from
actual runner results; this script contains no mocked responses or replay mode.
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from backend.agent.errors import MuseConfigurationError
from backend.agent.provider import MuseProvider
from backend.evaluation.config import EvaluationConfigurationError, PricingConfig
from backend.evaluation.models import CaseEvaluation
from backend.evaluation.runner import (
    DEFAULT_EVALUATION_DIRECTORY, DEFAULT_REPORT_PATH, EvaluationDatasetError,
    evaluate_cases, load_evaluation_cases,
)
from scripts.run_investigation import _redact_key, _reliability


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the deterministic held-out cases using the real Meta Model API.")
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_EVALUATION_DIRECTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--reliability", type=_reliability, default=1.0)
    return parser.parse_args(argv)


def _print_case(case: CaseEvaluation) -> None:
    if case.error is not None:
        text = f"{case.case_id}: ERROR ({case.error.code})"
    else:
        diagnosis = case.investigation.diagnosis
        text = (
            f"{case.case_id}: {diagnosis.status} / {diagnosis.likely_fault} | "
            f"exact={case.exact_diagnosis_correct}, abstention={case.abstention_correct}, "
            f"unnecessary={case.unnecessary_diagnosis}"
        )
    print(_redact_key(text), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cases = load_evaluation_cases(args.cases_dir)
        pricing = PricingConfig.from_env()
    except (OSError, UnicodeError, ValidationError, EvaluationDatasetError):
        print("Cannot load evaluation cases: check scenario schemas and unique case IDs.", file=sys.stderr)
        return 1
    except EvaluationConfigurationError:
        print("Invalid evaluation pricing configuration; configure both token prices together.", file=sys.stderr)
        return 1
    try:
        with MuseProvider() as provider:
            report = evaluate_cases(
                cases, provider, pricing=pricing, reliability=args.reliability,
                model=provider.config.model, on_case=_print_case,
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_redact_key(report.model_dump_json(indent=2)) + "\n", encoding="utf-8")
        print("AGGREGATE METRICS")
        print(_redact_key(report.metrics.model_dump_json(indent=2)))
        print(_redact_key(f"Report saved: {args.output}"))
        return 1 if report.metrics.failed_case_count else 0
    except MuseConfigurationError:
        print("Cannot initialize MuseProvider; check META_API_KEY and META_MODEL.", file=sys.stderr)
        return 1
    except OSError:
        print("Cannot save the evaluation report; check the output directory.", file=sys.stderr)
        return 1
    except Exception:
        print("Evaluation failed unexpectedly; no replacement diagnoses were generated.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Evaluation interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

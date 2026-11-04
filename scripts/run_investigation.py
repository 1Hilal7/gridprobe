"""Run one live investigation: python -m scripts.run_investigation [scenario.json].

Export META_API_KEY (and optionally META_MODEL) before running. This utility
does not load .env files. Running main() makes real Meta API requests; importing
the module or using --help does not. Trace output is printed after completion.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.agent.errors import GridProbeAgentError, MuseAPIError, MuseConfigurationError
from backend.agent.models import InvestigationResult
from backend.agent.orchestrator import MuseOrchestrator
from backend.agent.provider import MuseProvider
from backend.evidence.ledger import EvidenceLedger
from backend.scenarios.loader import DEFAULT_SCENARIO_DIRECTORY, load_scenario
from backend.tools.models import Reliability
from backend.tools.runtime import ScenarioToolRuntime


DEFAULT_SCENARIO = DEFAULT_SCENARIO_DIRECTORY / "case_001_connection_overheating.json"


def _reliability(value: str) -> float:
    try:
        return TypeAdapter(Reliability).validate_python(float(value))
    except ValueError:
        raise argparse.ArgumentTypeError("reliability must be a finite number between 0 and 1") from None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one real GridProbe investigation using the Meta Model API.")
    parser.add_argument(
        "scenario", nargs="?", type=Path, default=DEFAULT_SCENARIO,
        help=f"scenario JSON path (default: demo/scenarios/{DEFAULT_SCENARIO.name})",
    )
    parser.add_argument(
        "--reliability", type=_reliability, default=1.0,
        help="source reliability supplied to the runtime (default: 1.0 for deterministic scenario input; not diagnosis confidence)",
    )
    return parser.parse_args(argv)


def _redact_key(text: str) -> str:
    key = os.environ.get("META_API_KEY")
    if key:
        # JSON rendering can escape quotes/backslashes in a credential.
        for representation in sorted({key, json.dumps(key)[1:-1]}, key=len, reverse=True):
            text = text.replace(representation, "[REDACTED]")
    return text


def format_result(result: InvestigationResult) -> str:
    """Render only the public investigation result, never a scenario or config."""
    lines = [f"INVESTIGATION {result.case_id} / {result.panel_id}"]
    labels = {
        "MODEL_RESPONSE": "MODEL", "TOOL_CALL": "TOOL CALL",
        "TOOL_RESULT": "TOOL RESULT", "MAX_STEP_TERMINATION": "STEP LIMIT",
    }
    for step in result.trace:
        label = labels[step.kind]
        if step.phase == "FINALIZATION":
            label += " (FINALIZATION)"
        lines.extend(["", f"STEP {step.step_number} — {label}"])
        if step.tool_name is not None:
            lines.append(f"Tool: {step.tool_name} ({step.tool_call_id})")
        if step.kind == "TOOL_CALL" and step.tool_arguments is not None:
            lines.append(json.dumps(step.tool_arguments, indent=2, allow_nan=False))
        if step.tool_result is not None:
            lines.append(json.dumps(step.tool_result, indent=2, allow_nan=False))
        if step.assistant_content is not None:
            lines.append(step.assistant_content)
        if step.evidence_ids_added:
            lines.append("Evidence added: " + ", ".join(step.evidence_ids_added))
        if step.error is not None:
            lines.append(f"{step.error.code}: {step.error.message}")
    lines.extend(["", f"Termination: {result.termination_reason}", "", "EVIDENCE"])
    lines.extend(record.model_dump_json(indent=2) for record in result.evidence)
    if not result.evidence:
        lines.append("No evidence records collected.")
    lines.extend(["", "FINAL DIAGNOSIS", result.diagnosis.model_dump_json(indent=2), "", "TOKEN USAGE"])
    if result.usage.requests_with_usage:
        lines.append(result.usage.model_dump_json(indent=2))
    else:
        lines.append(f"Unavailable ({result.usage.request_count} model requests).")
    return _redact_key("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        # Drop evaluation annotations before constructing any runtime or provider.
        data = load_scenario(args.scenario).to_scenario_data()
    except (OSError, UnicodeError, ValidationError):
        # ValidationError can include the original case, including private labels.
        print("Cannot load scenario: use a readable UTF-8 JSON file matching the scenario schema.", file=sys.stderr)
        return 1

    try:
        ledger = EvidenceLedger()
        runtime = ScenarioToolRuntime(data, reliability=args.reliability, evidence_ledger=ledger)
        with MuseProvider() as provider:
            print("Decision-support prototype for qualified maintenance personnel.")
            print("Running one live investigation; the trace will print after completion.", flush=True)
            result = MuseOrchestrator(provider, runtime).investigate()
        print(format_result(result))
    except (MuseConfigurationError, MuseAPIError, GridProbeAgentError) as exc:
        print(_redact_key(f"Investigation failed: {exc}"), file=sys.stderr)
        return 1
    except Exception:
        # Keep unexpected exceptions from dumping config, scenario, or API bodies.
        print("Investigation failed unexpectedly; no diagnosis was produced.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Investigation interrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Evaluation orchestration: ground truth stays outside every agent runtime."""

from collections.abc import Callable, Sequence
from pathlib import Path

from backend.agent.errors import GridProbeAgentError
from backend.agent.orchestrator import InvestigationProvider, MuseOrchestrator
from backend.evaluation.config import PricingConfig
from backend.evaluation.models import CaseEvaluation, EvaluationError, EvaluationReport
from backend.evaluation.scoring import aggregate_metrics, score_investigation
from backend.scenarios.loader import load_scenario
from backend.scenarios.models import ScenarioCase
from backend.tools.runtime import ScenarioToolRuntime


DEFAULT_EVALUATION_DIRECTORY = Path(__file__).resolve().parents[2] / "demo/evaluation"
DEFAULT_REPORT_PATH = DEFAULT_EVALUATION_DIRECTORY / "results.json"


class EvaluationDatasetError(ValueError):
    """The evaluation dataset is empty or contains duplicate case IDs."""


def _validate_cases(cases: Sequence[ScenarioCase]) -> None:
    if not cases:
        raise EvaluationDatasetError("The evaluation dataset contains no cases.")
    if len({case.case_id for case in cases}) != len(cases):
        raise EvaluationDatasetError("The evaluation dataset contains duplicate case IDs.")


def load_evaluation_cases(directory: str | Path = DEFAULT_EVALUATION_DIRECTORY) -> list[ScenarioCase]:
    """Load JSON cases in filename order; exclude the generated results.json."""
    directory = Path(directory)
    if not directory.is_dir():
        raise EvaluationDatasetError("The evaluation directory does not exist or is not a directory.")
    cases = [load_scenario(path) for path in sorted(directory.glob("*.json")) if path.name != "results.json"]
    _validate_cases(cases)
    return cases


def select_evaluation_cases(cases: Sequence[ScenarioCase], case_ids: Sequence[str] | None) -> list[ScenarioCase]:
    """Select known IDs in dataset order; repeated selectors do not repeat paid work."""
    _validate_cases(cases)
    if not case_ids:
        return list(cases)
    selected = set(case_ids)
    if selected - {case.case_id for case in cases}:
        raise EvaluationDatasetError("One or more selected case IDs are not available.")
    return [case for case in cases if case.case_id in selected]


def _failed_evaluation(case: ScenarioCase, error: EvaluationError) -> CaseEvaluation:
    normal = case.hidden_ground_truth == "normal_or_insufficient"
    return CaseEvaluation(
        case_id=case.case_id, panel_id=case.panel_id, hidden_ground_truth=case.hidden_ground_truth,
        error=error, exact_diagnosis_correct=None if normal else False,
        abstention_correct=False if normal else None,
        unnecessary_diagnosis=False if normal else None,
    )


def _evaluate_case(
    case: ScenarioCase, provider: InvestigationProvider, reliability: float, *,
    retry_provider_failures: bool, on_retry: Callable[[str], None] | None,
) -> CaseEvaluation:
    errors: list[EvaluationError] = []
    max_attempts = 2 if retry_provider_failures else 1
    for attempt in range(1, max_attempts + 1):
        try:
            # Retries start with a new conversation/runtime/ledger, never partial state.
            runtime = ScenarioToolRuntime(case.to_scenario_data(), reliability=reliability)
            result = MuseOrchestrator(provider, runtime).investigate()
            evaluation = score_investigation(case, result)
        except Exception as exc:
            error = EvaluationError(
                code=exc.code if isinstance(exc, GridProbeAgentError) else "EVALUATION_FAILED",
                message="Investigation failed; no validated diagnosis was returned.",
            )
            errors.append(error)
            if error.code == "PROVIDER_FAILED" and attempt < max_attempts:
                if on_retry is not None:
                    on_retry(case.case_id)
                continue
            evaluation = _failed_evaluation(case, error)
        evaluation.attempt_count = attempt
        evaluation.attempt_errors = errors
        return evaluation
    raise AssertionError("Evaluation attempts must terminate with a result or error.")


def evaluate_cases(
    cases: Sequence[ScenarioCase], provider: InvestigationProvider, *,
    pricing: PricingConfig, reliability: float = 1.0, model: str | None = None,
    on_case: Callable[[CaseEvaluation], None] | None = None,
    retry_provider_failures: bool = False,
    on_retry: Callable[[str], None] | None = None,
) -> EvaluationReport:
    """Run sequential investigations, recording errors without fabricating diagnoses.

    Failed cases remain in accuracy/abstention denominators. Their unavailable
    trace/usage cannot contribute to averages or token totals. Each case gets a
    new runtime and ledger; the provider is caller-owned and may be reused.
    The live CLI opts into one PROVIDER_FAILED retry. All other callers retain
    single-attempt behavior unless explicitly enabled. No provider-level retry
    settings are changed. Failed-attempt usage is unavailable and never guessed.
    """
    _validate_cases(cases)
    scored: list[CaseEvaluation] = []
    for case in cases:
        evaluation = _evaluate_case(
            case, provider, reliability, retry_provider_failures=retry_provider_failures, on_retry=on_retry,
        )
        scored.append(evaluation)
        if on_case is not None:
            on_case(evaluation)
    return EvaluationReport(
        model=model, pricing=pricing, metrics=aggregate_metrics(scored, pricing), cases=scored,
    )

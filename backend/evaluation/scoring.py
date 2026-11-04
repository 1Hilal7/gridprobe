"""Score returned results against evaluation annotations without changing them."""

from collections.abc import Sequence
from decimal import Decimal

from backend.agent.models import InvestigationResult, ModelUsageSummary
from backend.evaluation.config import PricingConfig, TOKENS_PER_MILLION
from backend.evaluation.models import CaseEvaluation, EvaluationMetrics
from backend.scenarios.models import ScenarioCase


def score_investigation(case: ScenarioCase, result: InvestigationResult) -> CaseEvaluation:
    if (case.case_id, case.panel_id) != (result.case_id, result.panel_id):
        raise ValueError("Investigation identity does not match the evaluation case.")
    normal = case.hidden_ground_truth == "normal_or_insufficient"
    diagnosis = result.diagnosis
    existing_ids = {record.id for record in result.evidence}
    return CaseEvaluation(
        case_id=case.case_id, panel_id=case.panel_id, hidden_ground_truth=case.hidden_ground_truth,
        investigation=result.model_copy(deep=True),
        exact_diagnosis_correct=None if normal else (
            diagnosis.status == "DIAGNOSIS_READY" and diagnosis.likely_fault == case.hidden_ground_truth
        ),
        abstention_correct=diagnosis.status in ("NEEDS_MORE_EVIDENCE", "NO_ACTIONABLE_DIAGNOSIS") if normal else None,
        unnecessary_diagnosis=diagnosis.status == "DIAGNOSIS_READY" if normal else None,
        valid_evidence_references=sum(evidence_id in existing_ids for evidence_id in diagnosis.evidence_ids),
        total_evidence_references=len(diagnosis.evidence_ids),
        tool_call_count=sum(step.kind == "TOOL_CALL" for step in result.trace),
    )


def aggregate_usage(results: Sequence[InvestigationResult]) -> ModelUsageSummary:
    usage = ModelUsageSummary(
        request_count=sum(result.usage.request_count for result in results),
        requests_with_usage=sum(result.usage.requests_with_usage for result in results),
    )
    for field in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens"):
        values = [getattr(result.usage, field) for result in results if getattr(result.usage, field) is not None]
        setattr(usage, field, sum(values) if values else None)
    return usage


def estimate_api_cost(usage: ModelUsageSummary, pricing: PricingConfig) -> float | None:
    """Price observed input/output totals; reasoning is already inside output."""
    if any(value is None for value in (
        usage.input_tokens, usage.output_tokens,
        pricing.input_price_per_million, pricing.output_price_per_million,
    )):
        return None
    return float((
        Decimal(usage.input_tokens) * Decimal(str(pricing.input_price_per_million))
        + Decimal(usage.output_tokens) * Decimal(str(pricing.output_price_per_million))
    ) / TOKENS_PER_MILLION)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def aggregate_metrics(cases: Sequence[CaseEvaluation], pricing: PricingConfig) -> EvaluationMetrics:
    completed = [case for case in cases if case.investigation is not None]
    results = [case.investigation for case in completed]
    faults = [case for case in cases if case.hidden_ground_truth != "normal_or_insufficient"]
    normal = [case for case in cases if case.hidden_ground_truth == "normal_or_insufficient"]
    valid_references = sum(case.valid_evidence_references for case in cases)
    total_references = sum(case.total_evidence_references for case in cases)
    usage = aggregate_usage(results)
    usage_complete = bool(cases) and len(completed) == len(cases) and all(
        result.usage.requests_with_usage == result.usage.request_count
        and result.usage.input_tokens is not None and result.usage.output_tokens is not None
        for result in results
    )
    cost = estimate_api_cost(usage, pricing)
    return EvaluationMetrics(
        case_count=len(cases), completed_case_count=len(completed), failed_case_count=len(cases) - len(completed),
        fault_case_count=len(faults), normal_or_insufficient_case_count=len(normal),
        diagnosis_accuracy=_rate(sum(case.exact_diagnosis_correct is True for case in faults), len(faults)),
        correct_abstention_rate=_rate(sum(case.abstention_correct is True for case in normal), len(normal)),
        unsafe_or_unnecessary_diagnosis_rate=_rate(sum(case.unnecessary_diagnosis is True for case in normal), len(normal)),
        evidence_reference_validity=(100 * valid_references / total_references) if total_references else None,
        valid_evidence_references=valid_references, total_evidence_references=total_references,
        average_tool_calls=_rate(sum(case.tool_call_count for case in completed), len(completed)),
        average_request_count=_rate(usage.request_count, len(completed)),
        usage=usage, usage_complete=usage_complete,
        estimated_api_cost=cost, cost_is_partial=not usage_complete if cost is not None else None,
    )

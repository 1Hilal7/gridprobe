"""Guard generic sufficiency instructions, without pretending to test live reasoning."""

import re

from backend.agent.prompts import GRIDPROBE_DEVELOPER_PROMPT


def test_heating_observations_do_not_uniquely_establish_connection_cause() -> None:
    policy = GRIDPROBE_DEVELOPER_PROMPT.split("CONNECTION-RELATED CAUSE SUFFICIENCY", 1)[1].split("ABSTENTION", 1)[0]
    normalized = " ".join(policy.split())
    assert "Elevated temperature, temperature rise, balanced currents, and stable voltage" in normalized
    assert "even in combination" in normalized
    assert "do not uniquely establish a connection-related cause" in normalized
    assert "Do not issue DIAGNOSIS_READY for connection_related_overheating solely from those observations" in normalized
    assert "prefer NEEDS_MORE_EVIDENCE" in normalized
    assert "in missing_evidence" in normalized


def test_prompt_requests_discriminating_evidence_without_universal_vision_requirement() -> None:
    prompt = " ".join(GRIDPROBE_DEVELOPER_PROMPT.split())
    assert "localized visual/thermal evidence" in prompt
    assert "documented connection-specific maintenance finding" in prompt
    assert "another relevant independent observation" in prompt
    assert "Vision is not mandatory when strong independent connection-specific evidence already exists" in prompt
    assert "are not independent confirmations of the cause" in prompt
    assert "is not affirmative evidence of a connection defect" in prompt


def test_policy_has_no_case_annotations_or_new_electrical_thresholds() -> None:
    assert re.search(r"\b(?:CASE|EVAL)-\d+", GRIDPROBE_DEVELOPER_PROMPT) is None
    assert "hidden_ground_truth" not in GRIDPROBE_DEVELOPER_PROMPT
    assert "expected_relevant_evidence" not in GRIDPROBE_DEVELOPER_PROMPT
    policy = GRIDPROBE_DEVELOPER_PROMPT.split("CONNECTION-RELATED CAUSE SUFFICIENCY", 1)[1].split("ABSTENTION", 1)[0]
    assert re.search(r"\d", policy) is None


def test_existing_overload_and_phase_imbalance_instructions_remain() -> None:
    prompt = " ".join(GRIDPROBE_DEVELOPER_PROMPT.split())
    assert "elevated current alone does not prove overload" in prompt
    assert "phase imbalance alone does not prove a connection fault" in prompt
    assert "Never calculate phase imbalance yourself when the calculate_phase_imbalance tool is available" in prompt
    assert "Use deterministic tools whenever a numerical fact can be calculated or retrieved" in prompt

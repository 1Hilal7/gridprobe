# Evaluation methodology and measured results

GridProbe's evaluation compares real `InvestigationResult` objects with scenario annotations held outside the agent. It measures exact fault labeling, abstention, reference integrity, tool use, and reported inference cost. Automated tests use mocked providers; the reports below come from real Muse Spark 1.3 runs.

## Dataset and isolation

The repository contains four primary demos in `demo/scenarios/` and eight separate deterministic evaluation variants in `demo/evaluation/`, two for each incident class. Telemetry is simulated and fixed; there is no runtime randomness or live hardware requirement. Numerical patterns overlap, so a single measurement does not establish a unique cause.

`ScenarioCase` carries `hidden_ground_truth` and `expected_relevant_evidence` for evaluation. Before investigation, `to_scenario_data()` removes those fields. A fresh scenario-scoped runtime receives only this projection; the model starts with case/panel IDs and a current snapshot. History, maintenance context, and visual information require tools. Evaluation annotations and report objects are never model inputs or public product responses.

The expected-evidence annotations are not used as hints or as an evidence-selection score in the current harness. Public demo names are presentation labels, not initial agent evidence. Repository readers can inspect dataset files; “hidden” refers to exclusion from agent context, not secrecy from repository access.

## Latest full eight-case run

Source: [demo/evaluation/results.json](../demo/evaluation/results.json), generated **2026-11-04T20:45:24.507765Z**, model `muse-spark-1.3`. These saved measurements are not recomputed from mock tests or manually rewritten.

| Measure | Full run |
| --- | --- |
| Total cases | 8 |
| Completed / failed | 8 / 0 |
| Fault cases / normal-or-insufficient cases | 6 / 2 |
| `diagnosis_accuracy` | **66.67% (4/6)** |
| `correct_abstention_rate` | **100% (2/2)** |
| `unsafe_or_unnecessary_diagnosis_rate` | **0% (0/2)** |
| `evidence_reference_validity` | **100% (56/56)** |
| `average_tool_calls` | 8.875 |
| `average_request_count` | 6.0 |
| Reported model requests / requests with usage | 48 / 48 |
| Input / output tokens | 172,064 / 47,595 |
| Total reported tokens | 219,659 |
| Reported reasoning tokens, already inside output | 32,844 |
| Estimated API cost | **$0.41735875** |
| Usage complete / cost partial | false / true |

All four overload/phase-imbalance fault cases produced exact matches. The two connection-related overheating cases returned `NEEDS_MORE_EVIDENCE` with cause unknown: connection-specific visual evidence was unavailable, and heating with balanced currents and steady voltage did not distinguish the cause. Missing torque documentation was not treated as proof of a connection defect.

Those two fault-case abstentions score zero under the exact-label definition. They reflect the intended evidence-sufficiency policy, not a wrong fault label selected at random. **GridProbe prefers requesting more evidence over inventing a causal diagnosis.** Accuracy is still reported as 66.67%; the rubric is not changed to credit these as exact diagnoses.

Zero failed cases means all final case attempts completed. It does not mean there were no provider failures: four cases completed on a second attempt. Although all 48 returned requests expose usage, failed attempts did not always return their usage under the current error contract. That is why aggregate usage is incomplete and the cost is partial.

## Separate targeted normal-case follow-up

Source: [results_eval_004_eval_008.json](../demo/evaluation/reports/results_eval_004_eval_008.json), generated **2026-11-04T19:12:01.754109Z**. This earlier post-fix run selected only the two normal/insufficient variants. It is separate from, and chronologically before, the latest full run.

| Measure | Targeted subset only |
| --- | --- |
| Completed / failed | 2 / 0 |
| Correct abstentions | **2/2 (100%)** |
| Unnecessary diagnoses | **0 (0%)** |
| Evidence-reference validity | **100% (14/14)** |
| Average tool calls / requests | 8.0 / 5.0 |
| Reported total tokens | 43,989 |
| Estimated API cost | **$0.08690625** |
| Cost partial | false |

Exact fault-diagnosis accuracy is null for this subset because it contains no fault cases. These selected results are not a full benchmark, are not pooled with the eight-case run, and do not establish performance on unseen faults.

## Metric definitions

Implementation: `backend/evaluation/scoring.py`. Denominators remain unchanged.

| Metric | Definition |
| --- | --- |
| Exact diagnosis | For `overload`, `phase_imbalance`, or `connection_related_overheating`, count correct only when status is `DIAGNOSIS_READY` and `likely_fault` exactly matches the evaluation-only label. Divide by all fault-labeled cases. |
| Correct abstention | For `normal_or_insufficient`, count `NEEDS_MORE_EVIDENCE` or `NO_ACTIONABLE_DIAGNOSIS` as correct. Divide by all normal/insufficient cases. |
| Unnecessary diagnosis | For `normal_or_insufficient`, count status `DIAGNOSIS_READY`. Divide by all normal/insufficient cases. This is a status metric, not a certification of electrical safety. |
| Evidence validity | Percentage of final cited evidence-ID occurrences present in the same returned ledger: `100 × valid references / all references`. This is a micro-average across returned results. |
| Tool-call average | Count chronological trace events with kind `TOOL_CALL`; divide by completed investigations. Repeated calls still count even when evidence is deduplicated. |
| Model-request average | Sum returned usage `request_count`; divide by completed investigations. Includes investigation and finalization, plus Muse visual-observation requests when used by the current implementation. Failed attempts without returned usage are not invented. |

Accuracy and abstention rates are stored as fractions from 0 to 1; evidence-reference validity is stored as a percentage from 0 to 100. Empty denominators yield null rather than an invented perfect score. Failed cases remain in accuracy/abstention denominators and do not count as correct. Completed-case averages exclude failed investigations with no result.

Evidence-reference validity measures referential integrity, not whether the cited evidence is independent, persuasive, causally sufficient, or correctly interpreted. The orchestrator rejects nonexistent references before returning a validated result.

## Usage aggregation and cost

The harness sums available input, output, total, and reasoning tokens from returned investigations. Null means unavailable. `requests_with_usage` shows reported-request coverage. `usage_complete` additionally requires every case to complete on its first attempt and all returned requests to expose input/output usage. Retries therefore mark a calculable aggregate estimate as partial.

The centralized project Muse Spark 1.3 Standard defaults are **USD 1.25 per million input tokens** and **USD 4.25 per million output tokens**. These are the rates stored with both reports.

```text
estimated_api_cost = (
    reported_input_tokens × input_price_per_million
  + reported_output_tokens × output_price_per_million
) / 1,000,000
```

For the full report: `(172064 × 1.25 + 47595 × 4.25) / 1000000 = $0.41735875`. Reasoning tokens are already inside completion/output totals and are not double-charged. Cached-input usage is not available in the summary, so all reported input tokens are conservatively charged at the normal input rate. SAM segmentation charges and other unavailable fees are excluded.

If input/output totals or pricing are missing, the estimate is null. Missing failed-attempt usage is never guessed. `META_INPUT_PRICE_PER_MILLION` and `META_OUTPUT_PRICE_PER_MILLION` override rates as a pair; leaving both blank uses Standard defaults. `META_PRICE_CURRENCY` defaults to `USD`; another evaluation currency requires explicit prices, with no conversion. Product API estimates require USD.

## Retry behavior

The live evaluation CLI retries a failed case **once, only for category `PROVIDER_FAILED`**. It prints a credential-free retry notice and starts a new conversation, runtime, and ledger. Schema/validation, tool, and logic failures are not retried. Reports preserve `attempt_count` and `attempt_errors`. MuseProvider's global retry settings are unchanged. Programmatic `evaluate_cases()` remains single-attempt unless retry behavior is explicitly enabled.

A completed retried case contributes its final validated diagnosis to scoring. Unavailable failed-attempt tokens are excluded from observed sums, and the cost is marked partial. No replacement diagnosis is fabricated for failure.

## Reproduction

Install requirements and export the backend environment as described in the [README](../README.md#running-locally). The backend reads environment variables, not `.env` automatically. These commands make real Meta requests and consume credits:

```sh
python -m scripts.run_evaluation
python -m scripts.run_evaluation --case EVAL-008
python -m scripts.run_evaluation --case EVAL-004 --case EVAL-008
```

The full command loads the eight top-level input JSON files in filename order and saves `demo/evaluation/results.json`; the generated report is excluded from future dataset loading. Targeted runs save under `demo/evaluation/reports/` by default, preserving the full report. Repeatable `--case` selectors are validated before provider construction and deduplicated in dataset order.

Other flags: `--cases-dir`, `--output`, and `--reliability` (default 1.0, explicitly supplied source reliability, not diagnostic probability). To preserve the included full report during another full run:

```sh
python -m scripts.run_evaluation --output demo/evaluation/reports/full_rerun.json
```

Rerunning can change tool choices, wording, scores, usage, and cost. Saved reports contain actual returned diagnoses and evaluation-only annotations; never splice selected results into a full report or manually change its metrics.

## Validation and limitations

The current automated suite has **481 passing backend tests**, with all Meta calls mocked. Strict TypeScript checking and the production Vite build passed. Real dashboard smoke tests additionally cover CASE-002 and CASE-004; their individual costs and outcomes are documented in the [README](../README.md#product-experience), separately from the evaluation.

SAM segmentation and Muse descriptive image observation are implemented, but CASE-001's live asset is absent. Automated vision coverage is mocked and no completed live SAM/CASE-001 vision demonstration is claimed. The dataset is intentionally small and deterministic; it is not evidence of certified electrical diagnosis, deployment on live hardware, or field reliability. Confidence remains an uncalibrated model assessment.

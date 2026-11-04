# Scenario pack and evaluation

The four primary JSON cases are under `demo/scenarios`:

| Case | Panel | Evaluation ground truth |
| --- | --- | --- |
| CASE-001 | GP-021 | connection_related_overheating |
| CASE-002 | GP-017 | phase_imbalance |
| CASE-003 | GP-033 | overload |
| CASE-004 | GP-044 | normal_or_insufficient |

CASE-001, CASE-003, and CASE-004 use the user-specified measurements and
maintenance records exactly. Their unspecified telemetry date/timezone follows
the existing fixture convention: 2026-11-03, UTC+03:00. CASE-002 is unchanged.
CASE-001's image path is a future asset reference; no image observation is
fabricated and no vision operation is available yet.

Eight separate deterministic cases are under `demo/evaluation`. They are fixed
JSON inputs with two variants per class:

| Cases | Ground truth | Pattern |
| --- | --- | --- |
| EVAL-001, EVAL-005 | overload | Three phase currents increase together with temperature |
| EVAL-002, EVAL-006 | phase_imbalance | One phase diverges over time; affected phases A and C |
| EVAL-003, EVAL-007 | connection_related_overheating | Heating with similar phase currents; visual evidence unavailable |
| EVAL-004, EVAL-008 | normal_or_insufficient | A later temperature measurement without a persistent supporting history |

The variants use fixed numerical perturbations of their class's primary input,
including changes to voltage, current, and temperature values. No randomness,
electrical safety thresholds, or runtime label generation is used. Temperatures
and current magnitudes overlap between classes; investigation must consider
several observations. Variant measurement dates are 2026-11-04, UTC+03:00.
Ground truth and expected evidence annotations are for evaluation only. Only
`ScenarioCase.to_scenario_data()` enters a fresh runtime. The existing
orchestrator supplies just IDs and the current snapshot at the start.

## Running an evaluation

Install the existing requirements and export `META_API_KEY`, with `META_MODEL`
optional. No `.env` file is read. From the repository root:

```sh
python -m scripts.run_evaluation
```

The CLI loads the eight evaluation cases in filename order, runs a real Muse
investigation for each, prints per-case results and aggregate metrics, and
writes `demo/evaluation/results.json`. The generated report is excluded from
subsequent dataset loading. Optional flags are `--cases-dir`, `--output`, and
`--reliability` (default 1.0, a caller-supplied source reliability value).
The provider/client is shared sequentially, with a new runtime and ledger per
case. No label or result is used to alter the agent's reasoning policy.

Select one or more cases with repeatable `--case` options:

```sh
python -m scripts.run_evaluation --case EVAL-008
python -m scripts.run_evaluation --case EVAL-004 --case EVAL-008
```

Selectors are checked before a provider is created. Duplicate selectors run a
case only once, in dataset order. A targeted run defaults to a report under
`demo/evaluation/reports/`, preserving the existing full `results.json`.
For the two-case example, the filename is `results_eval_004_eval_008.json`.
`--output` explicitly overrides the destination. Nested reports are outside
the dataset loader's top-level JSON scan.

The live CLI retries a case once only when its error category is
`PROVIDER_FAILED`. It prints a credential-free retry notification. Each attempt
starts a fresh conversation, runtime, and ledger. Validation, diagnosis-schema,
tool, and logic failures are not retried. Provider-global retry settings remain
unchanged; programmatic `evaluate_cases` remains single-attempt unless its
`retry_provider_failures` option is explicitly enabled. Reports preserve
`attempt_count` and `attempt_errors`, including a failed first attempt followed
by success. Failed-attempt tokens are unavailable under the existing agent
contract, so retried runs have incomplete usage and partial cost estimates.

The report includes the evaluation label, returned investigation, per-case
scores or errors, pricing configuration, model name, timestamp, and aggregate
metrics. These evaluation report objects are never sent to the model.
`results.json` is produced by running the live CLI; saved real measurements are
never edited to reflect unmeasured behavior changes. Tests write mocked-run
reports only to temporary paths.

## Metric definitions

| Metric | Definition |
| --- | --- |
| diagnosis_accuracy | Correct `DIAGNOSIS_READY` plus exact fault label / all fault-labeled cases |
| correct_abstention_rate | `NEEDS_MORE_EVIDENCE` or `NO_ACTIONABLE_DIAGNOSIS` / all normal_or_insufficient cases |
| unsafe_or_unnecessary_diagnosis_rate | `DIAGNOSIS_READY` / all normal_or_insufficient cases |
| evidence_reference_validity | 100 × valid final evidence-ID references / all final references |
| average_tool_calls | Number of `TOOL_CALL` trace events / completed investigations |
| average_request_count | Reported model requests, including finalization / completed investigations |

Rates are fractions from 0 to 1; evidence validity is a percentage from 0 to
100. Evidence validity counts reference occurrences across all completed cases
(a micro-average). With no references or no applicable cases, the corresponding
metric is null. There is no invented perfect score for an empty denominator.
The unnecessary-diagnosis metric counts the specified status behavior; it does
not classify electrical safety.

Failed investigations are explicit error entries with no fabricated diagnosis.
They remain in accuracy/abstention denominators and do not count as correct.
Trace/request averages cover completed investigations only. Failed-case usage
is unavailable under the current orchestrator contract, and is not guessed.
The report includes completed and failed counts so these denominators are clear.

Abstention on connection-related heating without visual evidence remains
desirable under the existing agent policy. Under the requested exact-label
accuracy definition, abstention on a fault-labeled case scores zero. This
strict metric does not change the agent's abstention policy.

## Usage and pricing

Input, output, total, and reasoning token counts are summed when available.
Null means unavailable. `requests_with_usage` reports how many completed-case
requests supplied usage. `usage_complete` also requires all cases to complete
and each returned request to supply input/output usage. Partial sums are
reported explicitly; missing data is never silently treated as a measured zero.
Any failed/retried attempt also makes aggregate usage incomplete.

API and evaluation share centralized Muse Spark 1.3 Standard defaults:
USD 1.25 per million input tokens and USD 4.25 per million output tokens.
Source: [Meta Model API pricing](https://dev.meta.ai/docs/pricing-rate-limits).
Blank or unset price variables use these defaults. Configure both
`META_INPUT_PRICE_PER_MILLION` and `META_OUTPUT_PRICE_PER_MILLION` to override
them. `META_PRICE_CURRENCY` defaults to `USD`; another currency requires explicit
prices in that currency. No conversion is performed. An explicitly unpriced
`PricingConfig` is still supported for historical reports or unavailable rates.

The calculation is centralized in `backend/evaluation/scoring.py`:

```text
estimated_api_cost = (
    observed_input_tokens * input_price_per_million
    + observed_output_tokens * output_price_per_million
) / 1_000_000
```

Reasoning tokens already belong to completion/output totals and are not charged
again. If input/output totals or pricing are missing, cost is null. If usage
is incomplete, a calculable observed-usage estimate has `cost_is_partial=true`.
Other fees, caching discounts, and unavailable failed-request usage are not
inferred. Cached-input usage is unavailable in the current usage summary, so
all reported input tokens are conservatively priced at the normal input rate.
Pricing is stored with each report for reproducibility.

## Heating evidence and cause sufficiency

Temperature rise with similar phase currents and little voltage variation can
establish heating without distinguishing a connection-related cause. The
developer policy requests discriminating observations in this situation and
prefers `NEEDS_MORE_EVIDENCE`. Source temperature history and its derived trend
are not independent causal confirmations, and lack of support for other fault
types does not establish a connection defect. Strong independent connection-
specific maintenance or other evidence may establish that cause without vision.
Scenario data and scoring definitions are unchanged. Prompt tests check the
generic instruction contract; live behavioral improvement requires a measured
rerun and is not inferred from mocked tests.

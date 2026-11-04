# GridProbe

Evidence-Seeking AI Diagnostic Agent for Physical Infrastructure

Built for the Meta Global AI Developer Hackathon. GridProbe investigates electrical-panel incidents by selecting evidence, calling tools, and producing a traceable diagnosis only when the evidence is sufficient.

## Problem

Conventional anomaly detection can flag abnormal behavior, but an alert rarely answers the operator's next questions:

- What evidence should be collected next?
- Is the current evidence sufficient to identify a cause?
- When should the system abstain and request further inspection?

Different electrical causes can share symptoms. A temperature rise is an observation; identifying its cause requires additional evidence.

## What GridProbe Does

```text
OBSERVE → IDENTIFY UNCERTAINTY → SELECT NEXT EVIDENCE
        → CALL TOOL → REVIEW EVIDENCE → DIAGNOSE OR ABSTAIN
```

Muse Spark chooses which available tools to call. Each investigation starts with only the case ID, panel ID, and current telemetry snapshot. History, maintenance context, numerical analysis, and available visual observations must be requested through tools.

The final structured result uses one of three states:

- `DIAGNOSIS_READY`: evidence supports a specific diagnosis.
- `NEEDS_MORE_EVIDENCE`: additional observations are required.
- `NO_ACTIONABLE_DIAGNOSIS`: collected evidence does not support a specific actionable fault.

## Why GridProbe Is Different

| Capability | Role in GridProbe |
| --- | --- |
| Active evidence seeking | The agent selects the next observation to reduce uncertainty. |
| Deterministic numerical tools | Python calculates numerical facts without model arithmetic. |
| Muse Spark 1.3 reasoning | Selects tools, assesses sufficiency, and combines evidence. |
| SAM 3.1 segmentation architecture | Localizes components and supplies objective geometry. |
| Muse multimodal visual observation | Describes visible conditions without assigning electrical causes. |
| Evidence Ledger | Preserves numbered, typed observations and provenance. |
| Structured diagnosis | Validates final output and cited evidence IDs. |
| Explicit abstention | Requests more evidence rather than guessing a cause. |
| Hidden-ground-truth evaluation | Scores investigations outside the agent's context. |
| Usage and cost transparency | Reports available usage and configured cost estimates. |
| Hardware-ready architecture | Separates data, tools, evidence, and reasoning for future adapters. |

## Architecture

```text
React Industrial Console → FastAPI Product API → Muse Orchestrator
    → Scenario Tool Runtime → Evidence Ledger → Structured Diagnosis
```

| Available tool | Returns |
| --- | --- |
| `get_current_snapshot` | Current voltage, current, and temperature measurements |
| `get_sensor_history` | One requested sensor's timestamped history |
| `calculate_phase_imbalance` | Exact current-deviation calculation |
| `calculate_temperature_trend` | Signed temperature change, duration, and rate |
| `get_maintenance_context` | Recorded inspection context and notes |
| `inspect_component_image` | SAM component boxes and mask metadata |
| `inspect_visual_condition` | Muse visible-condition observations and image quality |

**Deterministic Python supplies numerical facts; SAM 3.1 localizes components; Muse visual observation describes appearance; the Muse GridProbe agent selects evidence, assesses sufficiency, reasons about causes, and diagnoses or abstains.** SAM geometry alone does not establish a fault. Neither visual tool runs automatically or requires the other to run first.

The orchestrator bounds investigation to eight model turns, then makes a separate, tool-free finalization call. Hidden evaluation annotations never enter the runtime or public API. See [architecture](docs/architecture.md) and [vision boundaries](docs/vision.md).

## Evidence Ledger

Observations receive sequential IDs such as `EV-001`. Each typed record includes source, type, timestamp, summary, value/unit, producing tool, reliability, and metadata. Retrieval and analysis preserve measurements; visual records distinguish localization from descriptive appearance. Repeated identical successful requests reuse evidence within an investigation.

The final diagnosis can only cite existing evidence IDs; unknown references fail validation. Reliability is supplied by the producer and differs from diagnostic confidence. Confidence is not a calibrated probability.

Measured evidence-reference validity in the latest full evaluation is **100%: 56/56 references exist in the returned ledgers**. This measures traceability, not whether every interpretation is correct.

## Meta Model API

The backend uses the OpenAI-compatible SDK against `https://api.meta.ai/v1` with environment-only credentials:

- **`muse-spark-1.3`** powers investigation tool selection, evidence reasoning, and structured finalization. A separate image-understanding provider returns validated objective visual observations from an image in a user message.
- **`sam-3.1`** supplies component segmentation through streamed Responses API requests and the official Python `meta_sam_parser`.

Real Muse dashboard investigations and evaluation runs have been completed. SAM and Muse visual providers are implemented and covered by mocked automated tests. **No live CASE-001 image asset is bundled, and no successful live SAM or CASE-001 visual demonstration is claimed.**

## Product Experience

The React industrial console presents:

1. **Physical System:** three-phase telemetry, history charts, and available inspection imagery.
2. **Agent Investigation:** chronological tool requests, results, evidence creation, and safe model-review summaries.
3. **Evidence Ledger:** source observations with numbered references and cited-record highlighting.
4. **Final Diagnosis / Additional Evidence Required:** status, likely fault, risk, confidence, reasoning summary, inspection guidance, and missing evidence.
5. **Usage and estimated API cost:** reported requests, tokens, and Muse cost estimates.

The UI waits for the completed investigation response before rendering the trace; it does not simulate streaming tool activity or expose private chain-of-thought.

Real dashboard smoke tests were completed with live Muse Spark 1.3:

| Demo | Observed result | Model requests | Total tokens | Estimated Muse cost |
| --- | --- | --- | --- | --- |
| CASE-002 Phase Imbalance | `DIAGNOSIS_READY`, `phase_imbalance`, HIGH risk, 85% internal confidence, 7 cited records | 6 | 27,271 | ~$0.05108 |
| CASE-004 Insufficient Evidence | `NEEDS_MORE_EVIDENCE`, cause unknown, 35% internal confidence, explicit requests for discriminating evidence | 6 | 26,008 | ~$0.04882 |

These are observed smoke-test outcomes, not fixed responses or guarantees for subsequent model runs.

## Evaluation

The latest full live run evaluates eight deterministic variants, two per incident class, independently from the four primary demos. Results are preserved in [the full report](demo/evaluation/results.json), generated **2026-11-04 20:45:24 UTC**.

| Metric | Latest full 8-case run |
| --- | --- |
| Completed / failed | 8 / 0 |
| Fault / normal-or-insufficient cases | 6 / 2 |
| Exact fault-diagnosis accuracy | **66.67% (4/6)** |
| Correct normal-case abstention | **100% (2/2)** |
| Unnecessary diagnosis rate | **0% (0/2)** |
| Evidence-reference validity | **100% (56/56)** |
| Average tool calls | 8.875 |
| Average model requests | 6.0 |
| Total reported tokens | 219,659 |
| Estimated API cost | $0.41735875, **partial** |

The two connection-related overheating cases returned `NEEDS_MORE_EVIDENCE` because discriminating connection-specific visual evidence was unavailable. Under exact fault-label scoring, those abstentions count as incorrect; all four overload/phase-imbalance cases were exact matches. This reflects intentional evidence-sufficiency behavior, not a randomly selected wrong fault label. **GridProbe prefers requesting more evidence over inventing a causal diagnosis.** The exact accuracy remains 66.67%; abstentions are not reclassified as correct diagnoses.

An **earlier targeted post-fix normal/insufficient follow-up**, reported separately in [the two-case report](demo/evaluation/reports/results_eval_004_eval_008.json), achieved 2/2 correct abstentions, zero unnecessary diagnoses, and 100% evidence validity (14/14), with estimated cost $0.08690625. It is a selected subset, not an additional full benchmark, and is not pooled with the eight-case results.

The full cost estimate is partial because failed provider attempts did not always expose usage. See [evaluation methodology, denominators, retries, and pricing](docs/evaluation.md).

## Demo Scenarios

| Demo | Panel | Public demo focus |
| --- | --- | --- |
| CASE-001 | GP-021 | Connection-related overheating investigation; visual asset currently unavailable |
| CASE-002 | GP-017 | Phase imbalance |
| CASE-003 | GP-033 | Overload |
| CASE-004 | GP-044 | Normal / insufficient evidence |

These are demonstration labels, not evidence sent to the agent. The public listing exposes only IDs, initial telemetry, and image availability. Evaluation annotations remain outside agent context.

## Safety

GridProbe is **decision-support software**. It does not autonomously control or manipulate electrical infrastructure.

**Inspection and electrical work must be performed by qualified personnel using appropriate safety procedures.** GridProbe is not a certified electrical diagnostic system; its outputs do not replace professional inspection, protection systems, or site safety procedures.

## Cost Transparency

The project's configured Muse Spark 1.3 Standard defaults are:

- **$1.25 / 1M input tokens**
- **$4.25 / 1M output tokens**

```text
estimated_cost_usd = (reported_input_tokens × 1.25
                    + reported_output_tokens × 4.25) / 1,000,000
```

Reasoning tokens are not double-charged when already represented in output usage. Estimates depend on provider-reported usage; missing usage is not fabricated. Failed attempts can make aggregate costs partial. Cached-input detail is unavailable in the summary, so reported input is conservatively priced at the normal input rate.

Observed dashboard examples cost approximately **$0.05108 for CASE-002** and **$0.04882 for CASE-004**. Estimates cover Muse investigation, finalization, and reported Muse image-observation requests; SAM charges are excluded. Configure both token prices together to override defaults.

## Running Locally

Use Python 3.13 (the tested backend version) and Node.js 20.19+ or 22.12+ for Vite. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
```

Edit your local `.env` and set `META_API_KEY` to your credential. Keep it private; no key belongs in frontend variables or committed files. `cp -n` preserves an existing `.env`.

**The backend does not automatically load `.env`.** Export its variables in the backend shell before starting the API. For the shell-compatible example file:

```sh
set -a
source .env
set +a
uvicorn backend.api.main:app --reload
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. `VITE_API_BASE_URL` defaults to `http://localhost:8000`. For a different API address, set it in the frontend environment or `frontend/.env.local`, then restart Vite. Never use a `VITE_` variable for Meta credentials.

| Variable | Current behavior |
| --- | --- |
| `META_API_KEY` | Required backend credential for live Meta requests |
| `META_MODEL` | Agent model; defaults to `muse-spark-1.3`. Dedicated vision identifiers remain fixed. |
| `META_INPUT_PRICE_PER_MILLION` | Optional input pricing override; blank uses Standard defaults when both prices are blank |
| `META_OUTPUT_PRICE_PER_MILLION` | Optional output pricing override; configure together with input price |
| `META_PRICE_CURRENCY` | Defaults to `USD`; product API requires USD |
| `FRONTEND_ORIGINS` | Comma-separated local CORS origins; defaults cover localhost/127.0.0.1 ports 5173 and 4173 |
| `VITE_API_BASE_URL` | Frontend API URL; defaults to `http://localhost:8000` |

`DEMO_SCENARIO` remains an example placeholder; the current product selects cases through the dashboard/API, not that variable.

Routes: `GET /health`, `GET /api/scenarios`, `POST /api/investigations` with `{"case_id":"CASE-002"}`, and `GET /api/scenarios/{case_id}/image` for available validated demo assets. API docs: `http://localhost:8000/docs`.

Optional live commands after exporting backend configuration:

```sh
python -m scripts.run_investigation
python -m scripts.run_evaluation
python -m scripts.run_evaluation --case EVAL-004 --case EVAL-008
```

Live commands use Meta credits. Full evaluation replaces `demo/evaluation/results.json`; targeted runs save separately by default. The default manual investigation is CASE-001 and can request further evidence while its image is absent.

## Tests

**481 backend tests passed.** Automated Meta requests are mocked; tests do not incur live inference calls.

Frontend validation passed:

- Strict TypeScript typecheck
- Vite production build

```sh
python -m pytest
cd frontend
npm run build
```

The frontend build script runs the typecheck before bundling.

## Repository Structure

```text
backend/
  api/          FastAPI product boundary
  agent/        Muse provider, orchestrator, prompt, and diagnosis contracts
  tools/        Runtime, schemas, and deterministic calculations
  evidence/     Typed records, converters, and ordered ledger
  scenarios/    Scenario loading and public data projection
  vision/       SAM and Muse observation providers
  evaluation/   Runner, scoring, usage, and pricing
frontend/       React + TypeScript industrial console
demo/
  scenarios/    Four primary demo inputs
  evaluation/   Eight inputs, full report, and targeted reports/
scripts/        Manual investigations, evaluations, and connectivity checks
tests/          Offline automated regression suite
docs/           Architecture, evaluation, vision, submission, and demo script
```

The scenario references `demo/assets/case_001_terminal.jpg`; the image asset is not bundled.

## Hardware-Ready Roadmap

Future work includes Serial telemetry, MQTT, Modbus, ESP32 / industrial gateways, thermal cameras, continuous monitoring, predictive maintenance, technician feedback, and CMMS integration. Potential domains include motors, HVAC, solar, battery systems, and pumps.

These are roadmap adapters and capabilities, not claims of implemented hardware deployment.

## Limitations

- Demo telemetry is deterministic and simulated; no live electrical hardware is required.
- CASE-001's live vision asset is not currently bundled.
- SAM and Muse visual providers are covered by mocked automated tests, not a completed live CASE-001 vision demonstration.
- The evaluation dataset is intentionally small: eight variants across four classes. Results are not a field-performance guarantee.
- Reference validity demonstrates traceability, not diagnostic correctness or sufficiency by itself.
- Model confidence is internal and uncalibrated; outputs and tool choices can vary across real runs.
- GridProbe is not a certified electrical diagnostic system.

## Origin

GridProbe builds on lessons learned from **GridGuard**, an earlier independently built anomaly-detection project. GridProbe is a new evidence-seeking diagnostic architecture, not a rename of GridGuard.

Submission materials: [architecture](docs/architecture.md), [evaluation](docs/evaluation.md), [submission copy](docs/submission.md), and [120-second demo script](docs/demo_script.md).

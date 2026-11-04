# GridProbe — submission copy

## 1. One-sentence pitch

GridProbe is an evidence-seeking AI diagnostic agent for physical infrastructure that decides what to inspect next and produces an evidence-cited diagnosis only when the available observations support it.

## 2. Description

GridProbe helps qualified maintenance teams move from an anomaly to an evidence-backed decision. Starting with an electrical panel's current telemetry, Muse Spark 1.3 chooses which evidence to retrieve next: sensor history, deterministic electrical analysis, maintenance context, or available visual inspection. Python tools calculate numerical facts, while an Evidence Ledger preserves observations and provenance. A separate finalization step produces a validated diagnosis that can cite only existing evidence IDs. When the cause remains uncertain, GridProbe requests discriminating evidence instead of guessing. The industrial console makes tool activity, references, missing evidence, and estimated inference cost inspectable. Eight live evaluation cases achieved 100% evidence-reference validity and normal-case abstention, with 66.67% exact fault accuracy. SAM segmentation and Muse visual-observation integrations are implemented with mocked automated coverage; a live CASE-001 image is not bundled.

## 3. Problem

Anomaly detection tells an operator that something changed. It often leaves three decisions unresolved: what to measure next, whether a cause is supported, and when to abstain. Electrical symptoms can overlap. Heating with balanced currents does not uniquely identify a connection-related cause.

## 4. Solution

GridProbe begins with IDs and a current snapshot. Muse selects controlled tools to retrieve additional evidence, reviews the results, and either investigates further or finalizes. Deterministic tools calculate phase imbalance and temperature trend. Retrieval, numerical analysis, maintenance context, and visual results become typed evidence records.

The final diagnosis must cite existing records. Missing references and invalid structured output fail validation. Insufficient evidence leads to `NEEDS_MORE_EVIDENCE` or `NO_ACTIONABLE_DIAGNOSIS`, rather than a forced fault label. The product is decision support for qualified personnel.

## 5. How Meta Model API is used

**Muse Spark 1.3 is central to the working investigation loop:** it selects tools, assesses evidence sufficiency, reasons across observations, and returns structured final output. Real dashboard smoke tests were completed for phase imbalance and insufficient evidence; real evaluation reports are included in the repository.

The visual architecture adds two separate capabilities: **SAM 3.1** localizes components through streamed Responses API calls and the official Python parser; **Muse Spark image understanding** returns objective visible-condition observations through a user image message. SAM geometry is not a causal diagnosis. The visual integrations have mocked automated coverage; no successful live SAM or CASE-001 visual run is claimed.

## 6. Architecture

React industrial console → FastAPI product API → Muse orchestrator → scenario tool runtime → Evidence Ledger → validated structured diagnosis or abstention.

Deterministic Python supplies numerical facts. SAM supplies localization. Muse vision describes appearance. The GridProbe agent combines evidence and decides whether a causal diagnosis is supported. Scenario annotations remain in the evaluation subsystem, outside agent and public API context. The current telemetry source is deterministic simulation; no physical hardware is needed to run the demo.

## 7. Innovation

GridProbe lets the agent decide which evidence to retrieve instead of stopping at a one-shot telemetry answer. Its contribution is the investigation process: bounded tool use, numerical calculations outside the model, explicit provenance, validated citations, and visible abstention. Usage and cost reporting make the inference process inspectable alongside the result.

The architecture builds on lessons from GridGuard, an earlier independently built anomaly-detection project. GridProbe is a new evidence-seeking diagnostic architecture, not a rename of GridGuard.

## 8. Evaluation and results

The [latest full live report](../demo/evaluation/results.json) contains eight completed cases, zero failed cases, six fault cases, and two normal/insufficient cases:

| Measure | Full run |
| --- | --- |
| Exact fault-diagnosis accuracy | 66.67% (4/6) |
| Correct normal-case abstention | 100% (2/2) |
| Unnecessary diagnoses | 0% (0/2) |
| Evidence-reference validity | 100% (56/56) |
| Average tool calls / model requests | 8.875 / 6.0 |
| Reported tokens | 219,659 |
| Estimated API cost | $0.41735875, partial |

Both connection-related fault cases requested more evidence because discriminating visual evidence was unavailable. Those abstentions score zero under exact diagnosis scoring; they are not relabeled as successful diagnoses. This demonstrates the intended sufficiency policy while preserving an honest 66.67% accuracy figure. Valid citations do not imply every interpretation is correct.

A separate earlier targeted normal-case follow-up achieved 2/2 abstentions, zero unnecessary diagnoses, and 100% evidence validity, at $0.08690625 estimated cost. It is not pooled into the full benchmark. Failed provider attempts make the full cost partial when usage is unavailable.

Verification: 481 backend tests passed, plus strict TypeScript checking and a Vite production build. Automated Meta requests are mocked. The dataset is small and does not establish field performance. [Methodology](evaluation.md) gives exact denominators and retry behavior.

## 9. Safety

GridProbe is decision-support software, not a certified electrical diagnostic system. It does not autonomously control or manipulate electrical infrastructure. Inspection and electrical work must be performed by qualified personnel using appropriate safety procedures. Confidence is an internal model assessment, not a calibrated probability or safety guarantee.

## 10. Roadmap

Future adapters include Serial, MQTT, Modbus, ESP32 and industrial gateways, and thermal cameras. Further capabilities include continuous monitoring, predictive maintenance, technician feedback, and CMMS integration. Motors, HVAC, solar, battery systems, and pumps are future domains. These are roadmap plans, not deployed hardware capabilities.

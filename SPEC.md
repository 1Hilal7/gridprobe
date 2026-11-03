# GridProbe

## Evidence-Seeking AI Diagnostics for Physical Infrastructure

### 1. Product Definition

GridProbe is an AI diagnostic agent for physical infrastructure.

Unlike traditional anomaly-detection systems that stop after identifying abnormal behavior, GridProbe actively investigates an incident.

It decides what evidence it needs next, calls deterministic tools to collect that evidence, optionally requests multimodal inspection, and produces a traceable diagnosis only when the available evidence is sufficient.

The first implementation domain is electrical panels.

The architecture must remain extensible to other physical systems such as industrial motors, HVAC systems, solar infrastructure, battery systems, pumps, and manufacturing equipment.

---

## 2. Core Product Principle

GridProbe must follow this loop:

OBSERVE  
→ IDENTIFY UNCERTAINTY  
→ SELECT NEXT EVIDENCE  
→ CALL TOOL  
→ REVIEW RESULT  
→ REQUEST MORE EVIDENCE IF NECESSARY  
→ DIAGNOSE OR ABSTAIN

The agent must not be implemented as:

telemetry → prompt → generic LLM diagnosis.

The evidence-seeking loop is the core innovation.

---

## 3. Hackathon Positioning

Primary theme:

Push the Frontier — Energy / Physical Systems

Primary track:

Indie Developer Track

Core differentiators:

- active evidence gathering
- deterministic tools combined with AI reasoning
- multimodal physical-system investigation
- explicit evidence ledger
- structured diagnosis
- ability to refuse diagnosis when evidence is insufficient
- measurable evaluation against hidden ground truth

---

## 4. User

Primary user:

Qualified maintenance technician or infrastructure operator.

GridProbe is a decision-support system.

It is NOT an autonomous electrical control system.

It must never automatically switch, energize, de-energize, repair, or physically manipulate electrical infrastructure.

Recommendations must be framed as inspection guidance for qualified personnel.

---

## 5. Hackathon MVP

The MVP must support four incident classes.

### Overload

Expected evidence may include:

- sustained high current across phases
- rising temperature
- relatively low phase imbalance

### Phase Imbalance

Expected evidence may include:

- one phase deviating significantly from others
- persistent imbalance over time
- otherwise normal or near-normal voltage

### Connection-Related Overheating

This is the primary demo scenario.

Expected investigation:

initial anomaly  
→ calculate phase imbalance  
→ retrieve current history  
→ retrieve temperature history  
→ determine evidence is still incomplete  
→ request or analyze inspection image  
→ identify affected component region  
→ produce evidence-backed diagnosis

### Normal / Insufficient Evidence

The agent must be able to return:

NEEDS_MORE_EVIDENCE

or

NO_ACTIONABLE_DIAGNOSIS

instead of inventing a fault.

This behavior is mandatory.

---

## 6. System Architecture

Data Source

SimulationTelemetrySource for hackathon.

Future adapters:

SerialTelemetrySource  
MQTTTelemetrySource  
ModbusTelemetrySource

The diagnostic architecture must not depend on simulated data.

Pipeline:

Telemetry Source  
→ deterministic tools  
→ Muse Spark agent  
→ evidence ledger  
→ diagnosis gate  
→ structured result  
→ frontend visualization

Optional multimodal branch:

Inspection image  
→ Muse visual reasoning  
→ SAM 3.1 component localization / segmentation  
→ visual evidence  
→ evidence ledger

---

## 7. Required Technologies

Backend:

Python  
FastAPI  
Pydantic

AI:

Meta Model API  
Muse Spark 1.3

Vision:

SAM 3.1 where feasible

Frontend:

React  
TypeScript  
Vite

Testing:

pytest

No production database is required for hackathon MVP.

Use deterministic JSON scenario files and in-memory session state.

---

## 8. Meta Model API Role

Muse Spark must be central to the product.

It is responsible for:

- reasoning about uncertainty
- selecting the next tool
- deciding whether sufficient evidence exists
- combining multiple evidence sources
- multimodal reasoning where applicable
- producing the final structured diagnosis

Muse must NOT calculate values that deterministic Python code can calculate reliably.

Examples:

Phase imbalance → Python tool

Temperature trend → Python tool

Historical sensor retrieval → Python tool

Fault reasoning → Muse

Evidence sufficiency → Muse

Final diagnosis → Muse

---

## 9. Agent Tools

The MVP exposes exactly these core tools.

### get_current_snapshot(panel_id)

Returns current telemetry.

### get_sensor_history(panel_id, sensor, minutes)

Returns deterministic historical sensor data.

Supported sensors include:

current_a  
current_b  
current_c  
voltage_a  
voltage_b  
voltage_c  
temperature

### calculate_phase_imbalance(panel_id)

Calculates imbalance using deterministic Python logic.

Returns numerical result plus interpretation metadata.

### calculate_temperature_trend(panel_id, minutes)

Returns:

start temperature  
end temperature  
absolute change  
rate of change

### get_maintenance_context(panel_id)

Returns limited contextual information such as:

last inspection date  
known previous alerts  
recent maintenance note

### inspect_component_image(panel_id, component)

Uses available multimodal infrastructure.

Target architecture:

Muse determines which component is relevant.

SAM localizes or segments that component.

The result becomes visual evidence.

---

## 10. Evidence Ledger

Every meaningful observation must become evidence.

Evidence schema:

id  
source  
type  
timestamp  
summary  
value  
unit  
tool_name  
reliability  
metadata

Possible sources:

TELEMETRY  
HISTORY  
DETERMINISTIC_ANALYSIS  
MAINTENANCE_CONTEXT  
VISION

Example:

EV-003

source: DETERMINISTIC_ANALYSIS  
type: PHASE_IMBALANCE  
value: 37.8  
unit: percent  
summary: Phase B differs substantially from the three-phase mean.

The final diagnosis must reference evidence IDs rather than only natural-language claims.

---

## 11. Diagnosis Output

The final AI output must use structured output.

Possible statuses:

INVESTIGATING

NEEDS_MORE_EVIDENCE

DIAGNOSIS_READY

NO_ACTIONABLE_DIAGNOSIS

ERROR

Final result schema must include:

status  
likely_fault  
risk_level  
confidence  
evidence_ids  
reasoning_summary  
recommended_inspection  
missing_evidence

Risk levels:

LOW  
MEDIUM  
HIGH  
CRITICAL

Confidence is an internal diagnostic confidence value from 0.0 to 1.0.

The UI must not portray confidence as verified probability unless evaluation supports that interpretation.

---

## 12. Agent Behavioral Rules

The system prompt must enforce:

Do not diagnose from a single ambiguous signal.

Prefer deterministic tools for numerical analysis.

Explicitly request additional evidence when uncertainty remains high.

Do not fabricate sensor values.

Do not fabricate maintenance history.

Do not fabricate visual observations.

Do not cite evidence that does not exist in the evidence ledger.

Return NO_ACTIONABLE_DIAGNOSIS when evidence contradicts or does not support a fault.

Never recommend unsafe electrical manipulation.

Recommendations must be inspection-oriented.

---

## 13. Scenario Engine

Scenario data must be deterministic and reproducible.

Each case contains:

case_id  
panel_id  
hidden_ground_truth  
initial_snapshot  
history  
maintenance_context  
optional_image  
expected_relevant_evidence

The hidden_ground_truth must never be provided to the agent.

The simulator must generate believable variation while preserving scenario semantics.

Hackathon evaluation should contain at least 12 cases.

Preferred target:

16–20 cases.

---

## 14. Evaluation

Required metrics:

Diagnosis Accuracy

Correct Abstention Rate

Evidence Selection Accuracy

Unnecessary Diagnosis Rate

Average Tool Calls

Optional:

Average investigation latency

Approximate Model API cost per investigation

All reported numbers must come from real evaluation runs.

Never manually modify reported evaluation results.

Evaluation outputs must be exportable to JSON.

The final README should report the final measured results.

---

## 15. Cost Tracking

Every Muse request should log usage when available.

Track:

input tokens  
output tokens  
reasoning tokens when available  
request count  
estimated cost

Create a small cost summary for evaluation runs.

The hackathon prototype should remain comfortably within the provided Meta credit.

Do not optimize away quality merely to minimize API usage.

---

## 16. Hardware Strategy

Hackathon:

No hardware dependency.

Use reproducible simulated telemetry.

Architecture must support future hardware.

Future physical architecture:

Electrical sensors  
→ edge controller / gateway  
→ MQTT or Modbus  
→ GridProbe telemetry adapter  
→ diagnostic agent

Possible future hardware:

isolated current sensing  
temperature sensing  
industrial voltage monitoring  
edge gateway  
visible or thermal camera

Real mains-voltage measurement must use appropriately certified and isolated equipment.

Do not design unsafe DIY mains connections as part of the project.

---

## 17. Frontend Product Design

The UI must look like an industrial operations product, not a generic hackathon dashboard.

Visual direction:

dark industrial console  
high information density  
strong hierarchy  
clean typography  
minimal decoration  
subtle motion  
no unnecessary gradients  
no emojis  
no generic AI chatbot layout

Suggested typography:

Geist or Inter

Numeric / telemetry:

Geist Mono

Primary application layout:

LEFT — Physical System

Current telemetry  
Trend graphs  
Panel context  
Inspection image

CENTER — Agent Investigation

Chronological investigation timeline:

anomaly observed  
tool selected  
tool result  
evidence added  
additional evidence requested  
diagnosis produced

RIGHT — Evidence Ledger

Evidence cards with:

ID  
source  
measurement  
summary

Top-level status area:

INCIDENT ID

INVESTIGATING / EVIDENCE NEEDED / DIAGNOSIS READY

Risk level

Likely fault

Confidence

Recommended inspection

---

## 18. UX Requirements

The user should understand within 10 seconds:

what is wrong  
what the AI is currently doing  
what evidence has been collected  
whether a diagnosis exists

Every agent tool call should become visible in the investigation timeline.

Loading states must be explicit.

Errors must be recoverable.

The interface must work on a typical laptop resolution used for the demo recording.

Responsive mobile support is desirable but not a hackathon priority.

---

## 19. Demo Scenario

Primary demo:

Connection-related overheating.

Desired sequence:

Panel GP-017 enters abnormal state.

Agent sees phase-current anomaly.

Agent calls calculate_phase_imbalance.

Agent determines that imbalance alone is insufficient.

Agent requests historical current.

Agent requests temperature history.

Evidence ledger gains multiple entries.

Agent determines visual evidence would increase diagnostic confidence.

Inspection image is analyzed.

Relevant component region is highlighted if SAM integration is available.

Agent returns:

DIAGNOSIS_READY

Likely fault:

connection-related overheating

Risk:

HIGH

Evidence IDs:

current imbalance  
temperature rise  
visual evidence

Recommended inspection:

Qualified inspection of the affected terminal area after safe isolation procedures.

---

## 20. Demo Reliability

Support deterministic demo scenarios.

Example environment variable:

DEMO_SCENARIO=connection_overheating

This fixes the input data.

It must NOT fake the Muse response.

Muse should still perform the real investigation.

If live API access fails during recording, the application may provide a clearly identified development replay mode using a previously captured real agent trace.

Do not present replayed output as a live API call.

---

## 21. Safety

GridProbe is not a certified electrical safety device.

The project must display an appropriate limitation statement.

It must not:

automatically control electrical infrastructure  
instruct unqualified users to interact with energized equipment  
claim guaranteed fault detection  
claim certified safety performance

Use wording such as:

“Decision-support prototype for qualified maintenance personnel.”

---

## 22. Repository Structure

gridprobe/

backend/
- api/
- agent/
- tools/
- evidence/
- scenarios/
- evaluation/
- vision/

frontend/
- src/components/
- src/features/
- src/hooks/
- src/api/
- src/types/

tests/

demo/
- scenarios/
- assets/

docs/
- architecture.md
- evaluation.md
- demo-script.md

SPEC.md  
README.md  
.env.example  
.gitignore

---

## 23. Coding Standards

Python:

type hints required  
Pydantic for external schemas  
small testable functions  
no business logic inside FastAPI routes  
clear separation between deterministic tools and AI reasoning

TypeScript:

strict types  
no any unless justified  
API types shared centrally  
components should remain small

Secrets:

never commit API keys

Use environment variables.

Required checks after significant changes:

backend tests  
frontend typecheck  
frontend build

---

## 24. Human-Owned Files

The following logic should not be invented autonomously by a coding agent without review:

fault scenario semantics

ground-truth labels

evidence interpretation

Muse system prompt

diagnosis safety rules

evaluation definitions

submission claims

demo narrative

These require explicit human approval.

---

## 25. Coding-Agent Rules

Codex or another coding agent must:

read SPEC.md before every major task

work only on the assigned scope

not redesign architecture without explicit approval

not invent new product features unless required to complete the assigned task

run relevant tests

report files changed

report assumptions

report unresolved issues

never insert API keys

never replace real evaluation with mocked results

---

## 26. Non-Goals for Hackathon

Do not build:

real autonomous electrical control

production authentication

billing system

multi-tenant SaaS

mobile app

large database infrastructure

20+ fault types

full digital twin

real industrial hardware installation

complex role management

These belong to future work.

---

## 27. Future Roadmap

Potential extensions:

real MQTT / Modbus ingestion

ESP32 or industrial gateway support

continuous monitoring

predictive maintenance

thermal-camera integration

technician feedback loop

fleet-level learning

CMMS integration

automatic maintenance-ticket generation

industrial-motor diagnostics

HVAC diagnostics

solar / battery diagnostics

edge inference

domain-specific evidence libraries

---

## 28. Commercial Direction

Potential product model:

hardware-agnostic diagnostic SaaS

Possible revenue components:

monthly monitoring subscription

per-site or per-panel subscription

enterprise deployment

edge gateway / installation fee

CMMS integrations

industrial support

AI inference is expected to be only one part of the total operational cost.

Hardware installation, industrial sensors, support, integration, and compliance may become larger cost drivers in production.

---

## 29. Final Hackathon Deliverables

The project is not complete until all of the following exist:

working backend

working Muse agent

real tool calling

evidence ledger

structured diagnosis

insufficient-evidence behavior

scenario engine

evaluation harness

measured evaluation results

usable frontend

primary demo scenario

README

architecture documentation

setup instructions

screenshots

demo video

English voiceover

English subtitles

submission description

limitations / safety section

cost summary

future roadmap

---

## 30. Product Statement

GridProbe should always be described as:

“An evidence-seeking AI diagnostic agent for physical infrastructure that decides what evidence it needs next, gathers that evidence through tools and multimodal inspection, and produces a traceable diagnosis only when the evidence is sufficient.”

Do not reduce the project description to:

“AI anomaly detector”

or:

“AI electrical-panel chatbot.”

The evidence-seeking investigation loop is the product.
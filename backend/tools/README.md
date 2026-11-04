# Scenario tool runtime

Create one `ScenarioToolRuntime(data, reliability=...)` per investigation, using
the plain `ScenarioData` returned by `ScenarioCase.to_scenario_data()`. The
runtime rejects subclasses and retains a private deep copy. Pass only
`runtime.initial_context().model_dump(mode="json")` as initial model context;
it contains `case_id`, `panel_id`, and `initial_snapshot`.

The five operations validate the active panel ID. History retrieval returns a
typed envelope with panel, sensor, requested minutes, and timestamp/value
points for that sensor only. Windows are inclusive, end at the snapshot time,
and exclude future points. Retrieval uses stored history only; the temperature
calculation additionally includes the current snapshot. Fractional, positive,
finite minute values are supported. Empty retrieval windows return no points;
analysis without positive duration raises the existing calculation error.
Aware timestamps are compared in UTC; naive timestamps require a shared clock.
Mixed awareness is rejected at initialization.

Deterministic calculations delegate to `electrical.py` and use the existing
evidence converters. Evidence timestamps use the snapshot timestamp. Reliability
is explicitly supplied by the caller and is not inferred. Retrieval operations
do not add evidence. The investigation owns `runtime.evidence_ledger`; consumers
may retrieve, list, or export its records, but should not insert independently.

Successful analysis requests are cached by tool, active panel, and validated
arguments. The fixed scenario makes the phase result a single cache entry;
temperature results are keyed by normalized float minutes (`60` and `60.0`
match). Repeats return independent result copies and reuse existing evidence.
Distinct windows create distinct evidence even if their measurements coincide.
Failures consume no ID or cache entry. IDs follow successful analysis insertion
order: `EV-001`, `EV-002`, etc. Each new runtime resets the sequence and cache.
Temperature evidence also records requested minutes separately from measured
duration, preserving which window was requested.

`get_tool_definitions()` returns fresh OpenAI-compatible JSON function
definitions for the five operations, using the same argument models as runtime
validation. They can be passed as `tools=` to `MuseProvider.chat_completion()`.
This module does not call the provider, dispatch model responses, or run an
agent loop.

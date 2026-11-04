# Scenario tool runtime

Create one `ScenarioToolRuntime(data, reliability=...)` per investigation, using
the plain `ScenarioData` returned by `ScenarioCase.to_scenario_data()`. The
runtime rejects subclasses and retains a private deep copy. Pass only
`runtime.initial_context().model_dump(mode="json")` as initial model context;
it contains `case_id`, `panel_id`, and `initial_snapshot`.

An optional `evidence_ledger=` argument accepts a caller-constructed empty
`EvidenceLedger`. The runtime otherwise constructs its own ledger as before.

The six operations validate the active panel ID. History retrieval returns a
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
is explicitly supplied by the caller and is not inferred. History and maintenance
retrievals also add evidence directly through their converters. Current snapshot
retrieval is unchanged. The investigation owns `runtime.evidence_ledger`; consumers
may retrieve, list, or export its records, but should not insert independently.

Successful evidence-producing requests are cached by tool, active panel, and
validated arguments. The fixed scenario makes phase and maintenance each a
single cache entry. History uses `(sensor, float minutes)` and temperature
analysis uses float minutes (`60` and `60.0` match). Repeats return independent
result copies and reuse existing evidence.
Distinct windows create distinct evidence even if their measurements coincide.
Failures consume no ID or cache entry. IDs follow successful evidence insertion
order: `EV-001`, `EV-002`, etc. Each new runtime resets the sequence and cache.
Temperature evidence also records requested minutes separately from measured
duration, preserving which window was requested.

History evidence uses `CURRENT_HISTORY`, `VOLTAGE_HISTORY`, or
`TEMPERATURE_HISTORY`, with amperes, volts, or Celsius units. Its scalar value
is null; metadata contains only the retrieved sensor's points, requested window,
first/last/minimum/maximum values, count, and actual start/end timestamps. Empty
retrievals are successful observations: count is zero, points are empty, and
statistics/time bounds are null. Maintenance evidence uses `MAINTENANCE_NOTE`,
copies the note into value, and preserves all recorded maintenance fields in
metadata, including nulls and original alert/note wording. Summaries add no
diagnostic interpretation. Both retrieval evidence timestamps use the current
snapshot time; historical measurement and inspection dates remain separate.

`get_tool_definitions()` returns fresh OpenAI-compatible JSON function
definitions for the six operations, using the same argument models as runtime
validation. They can be passed as `tools=` to `MuseProvider.chat_completion()`.
This module does not call the provider, dispatch model responses, or run an
agent loop.

`inspect_component_image(panel_id, concept)` uses an optional injected
`sam_provider=` or lazily creates the real SAM provider. Only a scenario-supplied
image inside `demo/assets` can be inspected. Requests cannot supply file paths.
The fixed six-tool interface reports `unavailable` for imageless panels or
missing assets, and a sanitized `error` for SAM failures; neither creates
evidence. A completed result, including zero objects, creates VISION evidence.
The normalized concept (lowercase, collapsed whitespace) is the visual cache
key within the fixed panel/image investigation. Repeats return `evidence_ids`
for the existing record and an empty `evidence_ids_added`, without another SAM
call. Distinct concepts create distinct records in the existing ID sequence.
See [the visual boundary](../../docs/vision.md) for output and path constraints.

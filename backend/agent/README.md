# Muse investigation orchestration

Create a `ScenarioToolRuntime` from a plain `ScenarioData` projection, supplying
reliability explicitly, then run:

```python
with MuseProvider() as provider:
    result = MuseOrchestrator(provider, runtime).investigate()
```

Use a fresh runtime for each investigation. The orchestrator only reads the
runtime's initial context, explicitly requested tool results, and ledger. Its
initial user message contains only case/panel IDs and the telemetry snapshot.
The existing DiagnosisResult contract is unchanged. The developer prompt includes
the generic visual-observation boundary documented below.

The seven functions are allowlisted. Each batch is validated against the existing
request models before any operation runs. Invalid JSON, duplicate JSON keys,
unknown tools, invalid arguments, and reused tool-call IDs are rejected. Batched
tools execute sequentially in response order, with one matching tool message
per call. Runtime caching deduplicates analysis/evidence while still allowing
the model to see the result of a repeated request.

`MAX_AGENT_STEPS = 8` counts investigation model turns, not individual calls in
a batch. Repeated model requests cannot extend the investigation beyond eight
turns. After a normal assistant response, or after completing the eighth batch,
a separate finalization request is made with no tools. The full conversation
is retained, and the exported ledger and formatting instructions are appended.
The SDK's `chat.completions.parse(response_format=DiagnosisResult)` requests
structured output and Pydantic parsing. There is no free-text fallback or
fabricated result if parsing fails or the endpoint rejects structured output.
Refusals, truncation, final tool calls, and nonexistent evidence citations are
also rejected. No additional diagnostic or fault rules are implemented.

Step-limit termination is recoverable: `MaxAgentStepsError` is recorded as a
typed error in the result and trace instead of being raised before finalization.
Finalization is explicitly told that the limit was reached and unsupported
certainty must be avoided. Other errors fail explicitly through agent-specific
exception classes. External exception text and API bodies are not propagated.

Trace numbers count events chronologically, including each model response,
tool call, tool result, final response, and step-limit event when applicable.
Tool results carry the runtime-generated evidence IDs added by that call.
Finalization and investigation events are distinguished by `phase`.

Usage sums available SDK input/output/total/reasoning token counts over both
phases and descriptive Muse vision requests. Null totals mean unavailable, and
`requests_with_usage` reports coverage.
Reasoning tokens are not double-counted in total tokens. No costs are estimated.
Provider/runtime ownership remains with the caller. Tests use scripted providers;
they never perform real Meta requests.

The sixth function, `inspect_component_image`, is selected by Muse like the
other tools. No code forces image inspection. Its result contains geometry
and evidence references, or a structured unavailable/error response so the
investigation can continue. SAM localizes components; it does not establish a
connection-specific cause. Reported model usage covers Muse calls, not SAM segmentation.

`inspect_visual_condition` is the seventh tool. It independently requests a
structured descriptive observation from Muse Spark's image understanding layer.
Only the image and requested component are sent to that provider; no telemetry,
scenario identity, evaluation annotations, or candidate diagnosis is supplied.
Visible connection-specific observations can help distinguish causes when
combined with telemetry and other evidence. SAM geometry alone is not causal
evidence. Neither visual tool is forced or required to precede the other.
Usage totals include the descriptive Muse vision requests, including requests
whose output is rejected. Unavailable usage remains unavailable/partial.

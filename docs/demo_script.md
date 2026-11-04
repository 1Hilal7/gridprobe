# GridProbe demo video — 120 seconds

English narration, on-screen actions, and subtitle text for a two-minute submission video. Use real application output. The previously verified dashboard examples are CASE-002 and CASE-004; new model runs may choose different tools or wording.

## Recording preparation

- Start the backend with exported environment configuration and the frontend with its correct API URL. Confirm backend connectivity; keep credentials, terminal environment output, and private model content out of frame.
- Record real CASE-002 and CASE-004 investigations. The console renders the tool trace after completion. Condense waiting periods in editing and label them **“Elapsed time condensed”**; do not make the UI appear to stream tool events that it does not stream.
- Keep scenario labels visible and make citations readable. Show actual returned status, references, usage, and cost. Do not insert a fixed diagnosis if the new live result differs.
- Use the architecture diagram for vision. CASE-001's asset is absent: do not show generated imagery, mocked output, or a successful live SAM claim.

## Narration and edit timeline

| Time | English narration | On-screen action | Subtitle text |
| --- | --- | --- | --- |
| 00–10 | “An anomaly tells us something changed. It does not tell us what evidence to collect next, or whether we know enough to identify the cause.” | Open on telemetry cards and an incident selected in the industrial console. | An anomaly is not a diagnosis. What evidence comes next? |
| 10–20 | “GridProbe is an evidence-seeking AI diagnostic agent. It observes, identifies uncertainty, selects tools, reviews evidence, then diagnoses or asks for more.” | Show the product name, then the observe → investigate → diagnose-or-abstain loop. | Observe → investigate → diagnose or abstain. |
| 20–55 | “Here is the phase-imbalance scenario. Muse Spark starts with the current snapshot and chooses what to retrieve. Python calculates the phase deviation and temperature trend. The agent checks history and maintenance context. Each observation gets an evidence ID. The final phase-imbalance diagnosis cites those records, and the console shows its risk, internal confidence, inspection guidance, and estimated Muse cost. We can inspect the path from measurement to conclusion.” | Select CASE-002 and show the real Run action. Cut any wait with the elapsed-time label. Pan across telemetry, completed tool requests/results, the ledger, cited evidence, and the final diagnosis. Briefly show usage. | Muse chooses tools. Python calculates facts. Every cited observation is traceable. |
| 55–75 | “Now consider insufficient evidence. Heating is observed, but the available measurements do not distinguish its cause. GridProbe returns NEEDS_MORE_EVIDENCE and requests discriminating observations. This is deliberate: balanced currents and rising temperature alone do not prove a connection fault.” | Switch to CASE-004; show its real completed result. Highlight NEEDS_MORE_EVIDENCE, unknown cause, and the missing-evidence list. | Cause not established. Request discriminating evidence instead of guessing. |
| 75–95 | “The architecture separates responsibilities. Muse selects evidence and assesses sufficiency. Deterministic tools provide numerical facts. SAM localizes components, while a separate Muse vision layer describes visible conditions. Those visual integrations are implemented and mock-tested; a live CASE-001 image demonstration is not included.” | Show the architecture diagram and the distinct numerical, SAM, Muse-observation, and ledger branches. Add “Vision: implemented; mocked automated coverage; live asset not bundled.” | Python: numerical facts. SAM: localization. Muse vision: visible observations. Agent: diagnosis or abstention. |
| 95–110 | “Eight live evaluation cases completed. Evidence references were 100 percent valid; normal-case abstention was 100 percent, with no unnecessary diagnoses. Exact fault accuracy was 66.67 percent: both connection-related cases requested unavailable discriminating evidence.” | Show the full-run metric table, emphasizing denominators: 56/56 references, 2/2 normal abstentions, 0/2 unnecessary diagnoses, 4/6 exact fault matches. | 8 completed · 56/56 valid references · 2/2 abstentions · 4/6 exact fault matches. |
| 110–120 | “GridProbe turns alerts into traceable investigations. Today it uses simulated telemetry; future adapters can connect physical infrastructure. Qualified personnel remain responsible for inspection and electrical work.” | Close on the console and product name. Show roadmap text and the qualified-personnel safety note. | Evidence first. Diagnose when supported. Physical telemetry adapters are future work. |

## Subtitle and claim checks

The subtitle column is a concise display alternative; for accessibility, export verbatim captions from the narration as well, split at natural phrase boundaries. Rehearse at approximately 130–145 words per minute and keep the final edit within 90–120 seconds. Adjust pauses and screen holds rather than omitting the abstention example or vision limitation.

The recorded smoke examples previously returned CASE-002 at 85% internal confidence, seven cited records, six model requests, 27,271 total tokens, and ~$0.05108; CASE-004 returned NEEDS_MORE_EVIDENCE at 35% confidence, six requests, 26,008 tokens, and ~$0.04882. Quote those numbers only when showing the matching real capture. Confidence is not calibrated probability. Do not blend these dashboard runs or the targeted follow-up with the full benchmark.

Final production items: record footage, record narration, export captions, verify redaction, review the rendered edit and audio, and upload the video. This document is the script, not a claim that the video has already been produced.

# SAM 3.1 visual evidence

The isolated `backend/vision` provider follows Meta's
[SAM API flow](https://dev.meta.ai/docs/cookbook/sam-api-basics) and
[official Python parser](https://dev.meta.ai/docs/sam/client-libraries).
It uses `AsyncOpenAI.responses.create` against `https://api.meta.ai/v1`
(`POST /v1/responses`), fixed model `sam-3.1`, a user message containing
`input_text` and an `input_image` data URL, and `stream=True`.
`meta-sam-parser==0.1.0` consumes the typed SDK events, including the live
`response.content_part.done` finalizer; GridProbe never parses the token grammar.
Incomplete responses, parser error diagnostics, invalid geometry, refusals,
and transport failures do not produce evidence. A completed zero-match does.

The provider returns a typed application result: concept, completion status,
unique object count, boxes, image dimensions, mask identifiers/encoding/size,
and diagnostic severity/line numbers when present. Raw output, compressed mask
payloads, arbitrary diagnostic messages, and SDK internals are excluded.
Boxes use displayed source-image pixels and half-open right/bottom coordinates.
The frontend renders box overlays, not decoded mask rasters. Masks remain
validated by the official parser and are represented by objective metadata.

`SamProvider.segment(path, concept)` is a synchronous adapter for the existing
synchronous runtime. Async callers may use `await segment_async(...)` instead.
Each owned async SDK client and stream is closed within its request; injected
clients remain caller-owned. Configuration is lazy and environment-only through
the existing `MetaConfig`; `META_MODEL` does not override the fixed SAM model.
No global Muse provider retry settings change. All errors use static messages.

## Tool and evidence boundary

`inspect_component_image` accepts only `panel_id` and `concept`. Concepts are
normalized component phrases of up to six words / 80 characters. Lexical guards
reject instruction syntax and explicit causal-condition phrases; this is not
a natural-language understanding classifier. For example, request
`electrical terminal`, not a condition to diagnose.

The tool is always described in the fixed six-tool schema, but inspection is
available only when the active ScenarioData supplies an accessible image.
Missing images yield `status: unavailable` and a safe error code; provider
failures yield `status: error`. Both allow Muse to continue with other data or
ask for more evidence. They consume no evidence IDs and are not cached as
successful observations. Completed results contain concept, objects_found,
boxes, mask_count, dimensions, safe image identifier, SAM model, evidence_ids,
and evidence_ids_added.

Completed visual requests add one `VISION` /
`VISUAL_COMPONENT_OBSERVATION` record through the runtime, using the existing
sequential IDs. The metadata stores the requested concept, measured object
count/boxes/mask metadata, safe image identifier, model, dimensions, and coordinate
system. Reliability is the caller-supplied source reliability, not SAM detection
confidence or a calibrated diagnostic probability. The timestamp is the scenario
snapshot time, not a claimed image capture time. Identical normalized concepts
reuse their record and avoid another SAM request in that investigation. A new
runtime starts a new cache. Demo assets are assumed fixed during investigation.

SAM supplies component localization only. It does not identify temperature,
terminal torque, connection integrity, electrical safety, or fault causality.
Muse decides which evidence to retrieve and whether the available independent
observations distinguish a cause. A terminal box alone does not establish
`connection_related_overheating`. Diagnosis contracts, prompt sufficiency rules,
fault labels, deterministic formulas, and evaluation scoring remain unchanged.

## Assets and public output

Only scenario-owned, repository-relative `demo/assets` references are resolved.
Absolute paths, parent traversal, backslash paths, and symlinks escaping that
area are rejected. Tool arguments cannot override an image path. Reads are
bounded to 20 MiB; Pillow verifies JPEG/PNG/WebP raster contents, limits images
to 40 million pixels, and obtains displayed EXIF dimensions. These are resource
limits, not electrical safety thresholds. No image is sent before validation.

The API exposes availability as a boolean and serves validated images through
an allowlisted primary-case route, never a client-supplied path. Images are
served with `nosniff` and `no-store`. Evidence uses `component-image.<extension>`
rather than the source filename, preventing scenario labels from leaking through
asset names. No image bytes, evaluation annotations, credentials, or raw parser
text enter agent context. The agent sees only requested geometry observations.

CASE-001's referenced asset is currently absent. No image was generated and no
live SAM request was made during implementation. Tests mock SAM transport or the
provider; one regression feeds a mocked official wire example through the actual
parser. Temporary test images are isolated from production demo assets.

Run the real check manually after supplying the asset and exporting META_API_KEY:

```sh
python -m scripts.check_sam_api demo/assets/case_001_terminal.jpg "electrical terminal"
```

It prints only the application segmentation summary and exits nonzero for image,
configuration, provider, or parsing failures. It never prints exception bodies.
The manual CLI intentionally accepts a user-provided local image path; the
agent-facing runtime and public image API always enforce the demo asset boundary.
Usage/cost fields in investigations remain Muse-only; SAM cost is not estimated
without a configured segmentation tariff. No fabricated usage is added.

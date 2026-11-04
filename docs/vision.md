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
`connection_related_overheating`. Diagnosis contracts, fault labels, deterministic
formulas, and evaluation scoring remain unchanged. The generic prompt addition
described below clarifies how descriptive visual observations may be combined
with other evidence.

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
text enter the investigation conversation. It receives only explicitly requested
geometry and descriptive visual observations through the two tools.

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

## Muse visible-condition observations (C10)

The separate `MuseVisualProvider` follows Meta's
[image-understanding format](https://dev.meta.ai/docs/image-understanding).
It calls `OpenAI.chat.completions.parse` at the existing Meta base URL, with
fixed model `muse-spark-1.3` and `response_format=VisualObservationResult`.
A developer message limits the task to visible properties. The USER message
contains a text part naming the component and an `image_url` part wrapping
`{"url": "data:image/...;base64,..."}`. No tool definitions, telemetry, scenario
IDs, maintenance context, SAM conclusions, or ground truth enter that request.
Image text is explicitly untrusted. Environment credentials/configuration are
reused; META_MODEL cannot redirect the fixed vision model. The existing
MuseProvider and SAM provider behavior are unchanged.

The result has exactly component, observations (feature, description, confidence),
and image_quality (SUFFICIENT, LIMITED, INSUFFICIENT). Unexpected fields, invalid
confidence, refusals, unparsed text, incomplete output, and diagnostic language
are rejected. Pydantic validation applies to the SDK response, runtime boundary,
and converter. The text guard rejects explicit diagnostic/safety terms and causal
phrases, including negated diagnoses. This is a lexical guard backed by strict
instructions, not a claim of exhaustive natural-language semantic verification.
INSUFFICIENT requires an empty observations list; it records the lack of assessable
visual detail rather than treating it as evidence of no anomaly. LIMITED permits
only the visible properties the model can describe. No confidence threshold
forces a diagnosis or observation.

`inspect_visual_condition` has its own component-keyed cache and the existing
sequential evidence ID scheme. It shares C09 path and raster protections.
Completed quality/observations become a separate VISION record with attribution
`vision_model: muse-spark-1.3`. Existing SAM records for the same normalized
component/image are linked in `sam_evidence_ids`. Links are captured at creation;
calling Muse observations before SAM is permitted and leaves an empty link list.
Neither tool runs automatically. No summaries describe electrical causes.

The roles remain distinct: SAM localizes; Muse vision describes appearance;
the GridProbe agent combines those observations with other evidence and decides
whether to diagnose or abstain. The minimal generic prompt addition says that
connection-specific discoloration, heat-like visible damage, deformation, or
strong asymmetry may discriminate a cause alongside telemetry and other evidence.
It explicitly excludes SAM geometry alone as causal evidence and prohibits
diagnosing from a visual observation alone. There are no case-specific rules.

The console labels the two record types separately. Muse observation request and
token usage is added to the existing investigation usage summary without counting
reasoning twice, so existing configured Muse pricing applies. SDK parsing failures
may have no returned usage; request coverage marks this limitation rather than
inventing tokens. SAM charges remain excluded. Injected observation providers
should be scoped to one runtime; SDK clients may remain caller-owned.

Manual live check (not executed during automated tests):

```sh
python -m scripts.check_visual_api IMAGE_PATH "electrical terminal"
```

It prints only the validated observation structure or a static, non-secret error.
CASE-001 still requires its real image asset. No live Meta request is part of the
automated verification, and mocked descriptions are not production observations.

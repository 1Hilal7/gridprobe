# GridProbe

Evidence-seeking AI diagnostic agent for physical infrastructure.

Built for the Meta Global AI Developer Hackathon.

## Core idea

GridProbe does not stop at anomaly detection.

It decides what evidence it needs next, gathers that evidence through deterministic tools and multimodal inspection, and produces a traceable diagnosis only when the evidence is sufficient.

## Status

Hackathon development in progress.

## Local development

Use a supported Python release (the backend is tested with Python 3.13). Install
`requirements.txt` in a virtual environment. Export `META_API_KEY` in the backend
shell; `META_MODEL` defaults to `muse-spark-1.3`. The backend reads environment
variables, not `.env` files. Then start the API from the repository root:

```sh
uvicorn backend.api.main:app --reload
```

Start the console in another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Use Node.js 20.19+ or 22.12+ for the Vite toolchain.
`VITE_API_BASE_URL` defaults to `http://localhost:8000`; set it in the frontend
environment or a local Vite env file for a different backend. Keep Meta keys
only in the backend environment, never in `VITE_` variables.

The four demo scenarios load from the backend. Each Run action performs a real
Muse investigation and returns the completed trace, evidence ledger, and
validated diagnosis. The console shows a waiting state during the synchronous
request; activity is displayed after completion. No canned diagnoses are used.

The product API provides `GET /health`, `GET /api/scenarios`, and
`POST /api/investigations` with body `{"case_id":"CASE-002"}`. API docs are at
`http://localhost:8000/docs`. Only public scenario fields are exposed. The trace
contains safe event summaries and tool observations; raw assistant reasoning
is excluded. Scenario history is returned to the UI after an investigation and
is never inserted into the agent's initial context.

Local CORS origins cover localhost/127.0.0.1 ports 5173 and 4173. Override the
comma-separated `FRONTEND_ORIGINS` on the backend when needed. Product cost
estimates default to USD 1.25 per million input tokens and USD 4.25 per million
output tokens in [Muse Spark Standard mode](https://dev.meta.ai/docs/pricing-rate-limits).
Set both `META_INPUT_PRICE_PER_MILLION` and `META_OUTPUT_PRICE_PER_MILLION` to
override these rates. `META_PRICE_CURRENCY` must be `USD` for the product API.
Reasoning tokens are already included in output totals and are not priced
again. Missing usage remains unavailable; partial estimates are labeled.
Source reliability is explicitly set to 1.0 for deterministic demo inputs,
separate from the model's internal diagnostic confidence.

CASE-001 reserves a visual inspection area. Image analysis and SAM are not yet
connected, and no visual observation is fabricated.

Validation:

```sh
python -m pytest
cd frontend
npm run build
```

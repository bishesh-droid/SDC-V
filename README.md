# SDC-V: Structural Design Copilot with Deterministic Verifier

SDC-V is a web application and JSON API that produces a draft reinforced-concrete (RCC) beam design to IS 456:2000 from either a structured form or a plain-English brief. A large language model (Google Gemini) is used only to extract fields from the brief and to narrate the result. All engineering numbers are produced by a deterministic Python calculator, all pass/fail verdicts are produced by a clause-tagged rule registry, and any model-written narrative is rejected if it contains a number that is not present in the verified result.

Every output is a draft. The tool does not certify, approve or sign off a design.

## Table of Contents

- Overview
- Architecture
- Project Structure
- Installation
- Configuration
- Usage
- API Documentation
- Data Flow Explanation
- Database Schema
- Testing
- Deployment
- Logging and Monitoring
- Security Considerations
- Performance Considerations
- Limitations
- Roadmap / Future Improvements
- Troubleshooting
- Contributing
- License

## Overview

### What problem it solves

Preliminary beam sizing and checking is repetitive and rule-based, but free-text briefs from clients and tender extracts are unstructured. Using a language model alone for the calculation is unreliable because it can produce plausible but wrong numbers. SDC-V separates the two concerns: the model handles language, and verified code handles every calculation and every compliance decision.

### Who it is for

- Structural engineers who want a fast, auditable first draft of a simple beam design for review.
- Developers and researchers evaluating guardrail patterns for LLM applications in a safety-relevant domain.

### Core capabilities

- Natural-language intake: converts a brief (plus an optional pasted specification) into structured fields, and asks for missing values instead of guessing.
- Structured-form intake that runs without any LLM or API key.
- Input guardrails: scope screening, unsafe-request refusal, prompt-injection flagging, PII redaction before text leaves the machine, grounding of extracted numbers, unit normalisation, and range validation.
- Deterministic flexure, shear, deflection and detailing design for singly reinforced rectangular beams.
- A registry of 19 verifier rules, each carrying an IS 456 clause reference, including two cross-checks that independently recompute design moment and effective depth.
- A deterministic reviser that enlarges the section (depth in 25 mm steps, then width, at most 8 revisions) until all error-level checks pass or the limit is reached.
- A report narrative written by the model but validated by a number-trace guardrail, with a deterministic template fallback.
- A generated SVG cross-section sketch.
- A SQLite audit log of every run, with an engineer review-logging endpoint.
- A benchmark of 60 cases covering golden, revision, incomplete, invalid, out-of-scope and prompt-injection categories.

### System boundaries

Supported design scope:

- Singly reinforced rectangular beams
- Simply supported or cantilever
- Uniformly distributed load only
- IS 456:2000, limit state method
- Concrete grades M20, M25, M30, M35, M40; steel grades Fe250, Fe415, Fe500

Not supported (detected and declined): T and L beams, doubly reinforced beams, continuous beams, slabs, columns, footings, prestressed concrete, point loads, seismic detailing (IS 13920), steel design, and other design codes.

Practical input limits (from `backend/app/schemas.py`): span up to 15 m (cantilever up to 6 m), width 150 to 1000 mm, depth 200 to 2000 mm, cover 20 to 100 mm, D/b not greater than 4, each of dead and live load up to 500 kN/m.

## Architecture

### High-level system architecture

The system is a single FastAPI process that serves both a JSON API and a static single-page frontend. There is no separate database server or message queue. The only external service is the Gemini REST API, called from the backend over HTTPS.

Textual diagram of the natural-language path:

1. Browser posts messages to `POST /api/chat`.
2. Deterministic scope screen on the user's own words. Out-of-scope or unsafe requests return immediately without calling the model.
3. Injection patterns are checked and logged; PII (emails, phone numbers) is redacted.
4. Intake LLM call extracts fields as JSON.
5. Grounding check drops any extracted number that does not literally appear in the user's text or attachment.
6. Normalisation converts units and validates ranges. Missing fields produce a follow-up question.
7. Calculator, rule registry and reviser loop produce a verified design.
8. Writer LLM call narrates the verified result; the number-trace guardrail accepts or rejects it, with up to 3 attempts and then a template fallback.
9. The full run is written to the SQLite audit log and returned to the browser.

The structured path (`POST /api/design`) skips steps 2 to 5 and the intake call, and uses the writer only when an LLM is configured.

### Backend architecture

- `app/main.py` defines the FastAPI application, request models and routes, and instantiates a single `AuditLog`, `GeminiClient` and `Pipeline` at import time.
- `app/pipeline.py` orchestrates the stages and defines `RunResult`, the single response model for every outcome.
- `app/llm/` holds the model client and the two prompt-driven agents (intake and writer).
- `app/guardrails/` holds the input guardrails and the output number-trace guardrail.
- `app/is456/` holds the calculator and the code tables. Both are pure Python with no I/O.
- `app/verifier.py` holds the rule registry. Rules recompute key quantities from raw input with their own formulas so that a fault in the calculator surfaces as a failed cross-check.
- `app/reviser.py`, `app/report.py`, `app/sketch.py`, `app/audit.py`, `app/schemas.py`, `app/config.py` hold the remaining supporting logic.

### Frontend architecture

A dependency-free static page (`frontend/index.html`, `app.js`, `styles.css`) served by FastAPI at `/` with assets under `/static`. It has two input tabs (free-text chat and structured form), a result view (verdict, section sketch, design values, verifier check table, revision timeline, narrative, guardrail events), an audit-log drawer, JSON download, print, and a review-logging form. Server-supplied strings are HTML-escaped in the client; the SVG sketch is generated by the server from numeric values and inserted as markup.

### Data layer

One SQLite file, `backend/data/audit.db`, created on first start. Each run is stored as a JSON record in a single `runs` table.

### Integration points and external services

- Gemini `generateContent` REST endpoint (`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`), authenticated with the `x-goog-api-key` header, called through `httpx`.
- No other external services.

### Design patterns used

- Pipeline / orchestrator (`Pipeline`).
- Protocol-based dependency injection for the model (`LLM` protocol), which allows a scripted `FakeLLM` in tests and a `None` model for structured mode.
- Decorator-based registry for verifier rules (`@rule`).
- Fail-closed fallback: rejected or unavailable model output is replaced by a deterministic template.
- Model-as-extractor: the model proposes, deterministic code validates (grounding, normalisation, range checks).
- Model fallback chain with retry (`GeminiClient`).

## Project Structure

### Root Directory

- `README.md` — This document.
- `.gitignore` — Excludes secrets (`.env`, `.env.*` except `.env.example`), local databases (`*.db`), Python caches, tooling state directories, and benchmark result outputs.
- `.env` — Local, untracked environment file. The configuration loader also reads this file (see Configuration).
- `SDC-V.docx`, `SDC-V.pdf`, `Structural_Design_Copilot.docx` — Project report documents. The pipeline description in this repository follows section 2.7 of the report, according to the previous README.

### /backend

- `requirements.txt` — Python dependencies: fastapi, uvicorn, pydantic, httpx, pytest (lower bounds only, no pinned versions).
- `.env.example` — Template for backend environment variables.
- `data/audit.db` — SQLite audit database, created at runtime. Untracked.

### /backend/app

- `__init__.py` — Package marker.
- `main.py` — FastAPI app, routes, request models, static mount.
- `config.py` — Environment loading (`.env` parsing), Gemini key and model list accessors, and constants: `APP_VERSION = "0.1.0"`, `MAX_REVISER_ITERATIONS = 8`, `MAX_WRITER_ATTEMPTS = 3`.
- `pipeline.py` — `Pipeline` class with `run_structured` and `run_chat`; `design_with_verification` loop; `RunResult` and `Iteration` models; `tool_versions()`.
- `schemas.py` — Pydantic models `BeamInput` (validated, unit-normalised input), `CheckResult`, `BarArrangement`, `Design`.
- `verifier.py` — 19 registered rules, `run_rules`, `RULE_META`, and `rules_fingerprint()` (a short SHA-256 over rule IDs and clauses, recorded in the audit log).
- `reviser.py` — Increases depth by 25 mm while D is within 3 times b and 2000 mm, otherwise increases width by 25 mm up to 1000 mm.
- `report.py` — Builds `ReportData` (pre-formatted strings), the draft `STAMP`, and the deterministic `template_narrative`.
- `sketch.py` — Generates the SVG cross-section from `BeamInput` and `Design`.
- `audit.py` — `AuditLog` over SQLite: save, list, get, review.

### /backend/app/llm

- `gemini.py` — `GeminiClient` (REST client with ordered model fallback, two attempts per model, retry on 429/500/503, temperature 0, 8192 max output tokens, 60 s timeout), the `LLM` protocol, `LLMError`, `parse_json`.
- `intake.py` — Intake system prompt, `IntakeResult`, `run_intake` (JSON mode, two parse attempts).
- `writer.py` — Writer system prompt and `write_report` (up to 3 attempts with number-trace validation, then template fallback).

### /backend/app/guardrails

- `input.py` — `RawIntake` and `Quantity` models, unit conversion tables (length to mm; load to kN/m), grade and exposure normalisation, `normalise`, scope and unsafe regex screens, injection patterns, PII redaction (email and phone), `numbers_in` for grounding.
- `output.py` — `trace_numbers`: every number in a narrative must occur in the strings of the verified `ReportData`.

### /backend/app/is456

- `calculator.py` — `design_beam`: loads, flexure with bar-arrangement iteration, shear, deflection, detailing, assumptions list.
- `tables.py` — IS 456 constants and tables: limiting neutral-axis ratios, cover and grade by exposure, tau_c,max, maximum bar spacing, basic span/depth ratios, `tau_c` closed-form fit of Table 19, and `deflection_modification` analytic fit of Fig. 4.

### /backend/tests

- `conftest.py` — Path setup, `base_input` fixture, scripted `FakeLLM`.
- `test_calculator_golden.py` — Calculator against coefficients, Table 19, round trips and hand calculations (9 tests).
- `test_verifier_mutation.py` — Verifies that injected calculator faults are caught by the rules (8 tests).
- `test_guardrails.py` — Input and output guardrail tests (12 tests).
- `test_pipeline_api.py` — Pipeline flows with a fake model and API endpoint tests (9 tests).

The suite reports 71 test results because some tests are parametrised.

### /frontend

- `index.html` — Page structure: header with model status pill, chat and form tabs, result container, audit drawer.
- `app.js` — Client logic: health check, chat and form submission, a minimal escaped Markdown renderer, result rendering, audit drawer, review submission, JSON download.
- `styles.css` — Styling.

### /benchmark

- `generate_cases.py` — Generates `cases.jsonl` (60 cases: 20 golden, 8 needs-revision, 10 incomplete, 8 invalid, 6 out-of-scope, 8 injection).
- `cases.jsonl` — The generated cases.
- `run_benchmark.py` — Runs cases against the pipeline. Flags: `--llm` to include chat cases through Gemini, `--baseline` to compare a plain, tool-less model on required steel area for golden cases.

## Installation

### System requirements

- Linux, macOS or Windows with Python 3.10 or later (the code uses `X | None` annotations and `from __future__ import annotations`).
- Network access to `generativelanguage.googleapis.com` for natural-language mode and LLM-written narratives.
- A Gemini API key for those two features. The structured form and template reports work without one.

### Steps

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY`. A key can be created at https://aistudio.google.com/apikey.

No database setup is required; the SQLite file and its directory are created on first start.

## Configuration

### Environment variables

- `GEMINI_API_KEY` — Gemini API key. Default: empty (natural-language intake disabled, template reports only).
- `GEMINI_MODELS` — Comma-separated, ordered list of model IDs. Each is tried in turn when one fails. Default: `gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite`.

### Constants in code

In `backend/app/config.py`: `MAX_REVISER_ITERATIONS = 8`, `MAX_WRITER_ATTEMPTS = 3`. The client timeout (60 s) is a constructor argument of `GeminiClient`.

### Loading order

`config.py` parses `backend/.env` first, then the repository-root `.env`, using `os.environ.setdefault`. Real process environment variables take precedence over both, and `backend/.env` takes precedence over the root file. The parser handles `KEY=value` lines, ignores comments, and strips surrounding quotes. Because values already in the environment are never overwritten, a stale `GEMINI_MODELS` line in a `.env` file overrides the code default.

### Secrets handling

`.env` files are git-ignored (only `.env.example` is tracked). The key is sent only in the `x-goog-api-key` request header and is not logged by the application.

## Usage

### Start the server

```bash
cd backend
python3 -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000. Add `--reload` for development. For a production-style run, bind explicitly, for example `--host 0.0.0.0 --port 8000`, behind a reverse proxy (see Deployment).

### CLI commands

```bash
cd backend && python3 -m pytest -q
cd benchmark && python3 run_benchmark.py
cd benchmark && python3 run_benchmark.py --llm
cd benchmark && python3 run_benchmark.py --baseline
cd benchmark && python3 generate_cases.py
```

### API examples

```bash
curl http://localhost:8000/api/health

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","text":"Simply supported beam, 6 m span, 300 x 550 mm, cover 30 mm, M25 concrete, Fe500 steel, dead load 15 kN/m, live load 12 kN/m, moderate exposure."}]}'

curl -X POST http://localhost:8000/api/design \
  -H "Content-Type: application/json" \
  -d '{"span":{"value":6,"unit":"m"},"support":"simply_supported","b":{"value":300,"unit":"mm"},"D":{"value":550,"unit":"mm"},"cover":{"value":30,"unit":"mm"},"fck":25,"fy":500,"dead_load":{"value":15,"unit":"kN/m"},"live_load":{"value":12,"unit":"kN/m"},"exposure":"moderate"}'

curl http://localhost:8000/api/runs?limit=10
curl http://localhost:8000/api/runs/RUN_ID

curl -X POST http://localhost:8000/api/runs/RUN_ID/review \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"Eng. Name","note":"Checked"}'
```

## API Documentation

All routes are under the same origin. No authentication is applied.

### GET /api/health

- Response 200: `{"ok": true, "llm_configured": bool, "models": [...], "code_edition": "IS456:2000", "versions": {...}}`. `versions` contains app version, Python version, pydantic version, code edition and rules fingerprint.

### GET /api/rules

- Response 200: list of `{"rule_id", "title", "clause", "severity", "revisable"}` for all 19 rules.

### POST /api/design

- Request body (`RawIntake`): `span`, `b`, `D`, `cover`, `dead_load`, `live_load` as `{"value": number, "unit": string}`; `support` string (`simply_supported` or `cantilever`); `fck` and `fy` as number or string such as "M25"; `exposure` (`mild`, `moderate`, `severe`, `very severe`, `extreme`). All fields are optional at the schema level; missing ones produce a `needs_info` result.
- Response 200: `RunResult` (below).
- Status codes: 200 for every pipeline outcome (including rejected, out-of-scope, needs-info); 422 for a body that fails schema validation (for example a non-numeric `value`).

### POST /api/chat

- Request body: `{"messages": [{"role": "user|assistant", "text": string (max 8000)}, ...] (1 to 20 items), "attachment_text": string (max 20000, default "")}`.
- Response 200: `RunResult`.
- Status codes: 200, 422 for schema violations. Model unavailability is reported inside the body with `status: "error"`, not as an HTTP error.

### GET /api/runs

- Query: `limit` (default 50, clamped to 1 to 200).
- Response 200: list of `{id, created_at, status, mode, summary, reviewer}` ordered by newest first.

### GET /api/runs/{run_id}

- Response 200: the full row with `record` parsed to an object (`result`, `versions`, `llm_model`, plus mode-specific extras such as `messages`, `intake`, `raw_input`).
- Response 404: `{"detail": "run not found"}`.

### POST /api/runs/{run_id}/review

- Request body: `{"reviewer": string (2 to 120), "note": string (max 2000, optional)}`.
- Response 200: `{"ok": true}`. Response 404 if the run does not exist. Response 422 for invalid body.
- This records a name and note in the audit log. It is not a certification.

### GET /

Serves `frontend/index.html`. Static assets are served at `/static/*`.

### RunResult

Fields: `run_id`, `status`, `mode` (`structured` or `chat`), `message`, `question`, `missing`, `errors`, `out_of_scope`, `conversions`, `original_input`, `final_input`, `design`, `checks`, `iterations`, `report`, `narrative`, `narrative_source` (`llm` or `template`), `sketch_svg`, `guardrail_events`, `llm_model`, `stamp`.

`status` values:

- `designed` — all error-level checks pass.
- `needs_engineer` — an error-level check failed that cannot be resolved by resizing, or the revision limit or size limits were reached.
- `needs_info` — required fields are missing, or loads appear factored; `question` carries the follow-up.
- `rejected` — input failed range or unit validation; `errors` lists reasons.
- `out_of_scope` — unsupported feature.
- `refused` — request to approve, certify, reduce safety margins, remove structural elements or skip inspections.
- `error` — the model is not configured or could not be reached or parsed (chat mode).

### Error handling

Domain errors are returned as 200 responses with a descriptive `status`. FastAPI/Pydantic return 422 for malformed bodies. The only explicit HTTP exceptions are the two 404 responses.

## Data Flow Explanation

### How data enters

Through `POST /api/chat` (free text and optional pasted attachment) or `POST /api/design` (structured fields).

### How it is processed

1. Chat only: scope and unsafe regex screens run on the user's own words (not on the attachment). Matches return immediately with no model call.
2. Chat only: injection patterns are matched against the brief and attachment and logged as `injection_suspected` events. The attachment is passed to the model inside `<attachment>` tags with a system rule that it is data, not instructions.
3. Chat only: emails and phone numbers are replaced with `[email]` and `[phone]` before transmission.
4. Chat only: the intake call returns JSON with an `intent` and field values in the user's original units.
5. Chat only: grounding. Each numeric field (span, b, D, cover, loads, fck, fy) must match a number found in the user's text or attachment, otherwise it is nulled and an `ungrounded_values_dropped` event is logged.
6. Chat only: if the model reports the loads as factored, the user is asked for characteristic loads.
7. Normalisation converts units to mm, m and kN/m, maps grade strings and aliases, and validates through `BeamInput`.
8. `design_with_verification` runs the calculator and all rules. If error-level rules fail and all failures are revisable, the reviser grows the section and the loop repeats, up to 8 revisions.
9. `report.py` converts the result into `ReportData` strings. The writer model receives only this JSON.
10. The number-trace guardrail checks the narrative and the draft stamp. On failure it re-prompts with the offending numbers, up to 3 attempts, then uses the template.

### Where it is stored

Each run is serialised into `runs.record` in `backend/data/audit.db`, with tool and rules versions and the model name.

### How it is returned

The `RunResult` is returned as JSON, including the SVG sketch and the narrative. The browser renders it and can fetch history from `/api/runs`.

## Database Schema

SQLite, one table, created by `AuditLog` if absent:

```sql
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, mode TEXT NOT NULL,
  summary TEXT, record TEXT NOT NULL, reviewer TEXT, reviewed_at TEXT, review_note TEXT
);
```

- `id` — 12-character hex run ID (primary key; implicit unique index).
- `created_at` — UTC ISO-8601 timestamp.
- `record` — JSON text: `result` (the full `RunResult`), `versions`, `llm_model`, and extras (`raw_input` in structured mode; `messages`, `attachment_chars`, `intake` in chat mode).
- `reviewer`, `reviewed_at`, `review_note` — set by the review endpoint.
- There are no foreign keys and no secondary indexes. Listing sorts by `created_at` without an index.
- Writes use `INSERT OR REPLACE` under a process-local lock; there is no migration system.

## Testing

```bash
cd backend
python3 -m pytest -q
```

The suite does not call the network. The model is replaced by `FakeLLM` or `None`. Last run in this repository: 71 passed.

Coverage notes:

- Calculator is tested against limiting-moment coefficients, Table 19 values, a flexure round trip, a SP 16-style value and a hand calculation.
- Verifier is tested by mutation: injected calculator faults must be caught.
- Pipeline tests cover hallucinating writer fallback, accepted writer output, incomplete briefs, dropped hallucinated extractions, attachment injection, out-of-scope and unsafe bypass of the model, invalid input, structured mode, and the API endpoints.

Benchmark (`benchmark/run_benchmark.py`): runs without a key for structured and deterministic-screen cases. Chat categories (incomplete, injection) need `--llm` and a key.

Missing tests:

- No automated test calls the real Gemini API.
- No frontend tests.
- Worked examples from textbooks are not yet included as golden fixtures (stated in the previous README).
- No coverage tooling is configured, and no CI runs the tests.

## Deployment

No Dockerfile, compose file, process manager configuration or CI/CD pipeline exists in the repository. A minimal deployment is:

1. Provision Python 3.10 or later.
2. Install `backend/requirements.txt` into a virtual environment.
3. Provide `GEMINI_API_KEY` (and optionally `GEMINI_MODELS`) through the process environment rather than a file.
4. Run `uvicorn app.main:app --host 127.0.0.1 --port 8000` under a process supervisor.
5. Place a reverse proxy in front that terminates TLS and adds authentication and rate limiting, since the application has neither.
6. Persist and back up `backend/data/`.

The application serves the frontend from the path `../frontend` relative to `backend`, so the directory layout must be preserved.

Scaling considerations: SQLite with a process-local lock supports a single instance. Running multiple workers works for reads but the lock does not coordinate between processes; use a server database before scaling horizontally.

## Logging and Monitoring

- No logging framework is configured; the application does not emit structured logs of its own beyond uvicorn's access log.
- The audit log is the primary record: inputs, guardrail events, verdicts, model name, tool versions and rules fingerprint.
- `guardrail_events` in each result record events such as `injection_suspected`, `pii_redacted`, `ungrounded_values_dropped`, `number_trace_rejected`, `writer_llm_error`, `fallback_template`, `intake_llm_error`.
- No error tracking, metrics or tracing is integrated. `/api/health` reports whether a key is configured, not whether the model is reachable.

## Security Considerations

- Authentication and authorization: none. All endpoints, including audit history and review logging, are open to any client that can reach the server.
- Input validation: Pydantic models on all endpoints; length limits on chat messages (8000 characters, 20 messages, 20000-character attachment); range and enum validation on engineering inputs.
- Prompt injection: attachment text is delimited and declared as data; regex flags are logged but not blocking; extracted numbers are grounded against the original text; the model never produces numbers that reach the design; the narrative is number-traced. The regex screens are heuristic and bypassable by paraphrase.
- PII: emails and phone numbers are redacted before being sent to the model. Names, addresses and other identifiers are not redacted.
- Rate limiting: none. Each chat request triggers up to several paid model calls.
- CORS: not configured; the frontend is same-origin.
- Secrets: the API key is read from the environment or `.env` and sent as a request header. Do not commit `.env`.
- Known issues:
  - The audit record stores the original, unredacted user messages in chat mode (`extra["messages"]`), so redacted PII persists locally.
  - `GET /api/runs/{id}` exposes the stored record to any caller.
  - Dependencies are unpinned.
  - The review field accepts any name; it is a log entry only.

## Performance Considerations

- The calculator and rules are pure computation and complete in milliseconds; the 71-test suite runs in under a second.
- Latency is dominated by model calls. A complete chat run (intake plus writer) measured about 25 seconds on `gemini-3.5-flash` during verification; a structured run without a model is near-instant.
- Endpoints are synchronous `def` functions, so FastAPI runs them in its thread pool. Each model call blocks a worker thread for its duration.
- The client waits up to 60 s per attempt, with two attempts per model across the fallback chain. If an earlier model in the list hangs rather than errors, a request can take minutes before reaching a working model. Order `GEMINI_MODELS` with responsive models first.
- No caching. Identical briefs trigger new model calls.
- SQLite opens a new connection per operation.

## Limitations

- Scope is limited to singly reinforced rectangular beams under UDL (see Overview).
- The deflection modification factor and Table 19 shear strength use analytic fits, not the code's chart and table values.
- Table 5, 15, 16 and 20 values and the maximum clear spacing values were entered manually and, according to the previous README, should be verified against the printed IS 456:2000.
- Design shear is taken at the support face (conservative). Span is the user-supplied effective span.
- Fixed assumptions: 8 mm 2-legged stirrups, 20 mm aggregate, 12 mm hanger bars, 25 kN/m3 concrete, bar diameters 12, 16, 20, 25, 32 mm.
- The grounding check compares numeric values only; it cannot detect a correct number assigned to the wrong field.
- The number-trace guardrail accepts any number present anywhere in the result, not only the number belonging to the check being described.
- The previous README states the chat-mode benchmark categories had not been run with a live model before this verification.
- Unfactored versus factored loads depend on the model's reading of the brief.
- No authentication, rate limiting, containerisation or CI.

## Roadmap / Future Improvements

Based on the current state of the code:

- Add textbook worked examples as golden fixtures and verify the code tables against the standard.
- Replace the analytic fits for Table 19 and Fig. 4 with the tabulated values, or document their error bounds.
- Add authentication, rate limiting and a reverse-proxy configuration.
- Redact PII from the stored audit messages, or store only redacted text.
- Add a Dockerfile, pinned dependencies and a CI workflow running pytest.
- Add structured logging and a health check that tests model reachability.
- Add a per-request timeout budget across the model fallback chain.
- Add tests with recorded Gemini responses for the intake and writer prompts.
- Extend scope features currently refused: T-beams, doubly reinforced and continuous beams.

## Troubleshooting

- `/api/health` shows `llm_configured: false` or the UI shows "Gemini key missing": `GEMINI_API_KEY` was not found in the environment, `backend/.env` or the root `.env`.
- Chat returns `status: error` with "language model could not be reached": check `guardrail_events` for `intake_llm_error`. The detail contains the per-model failure.
- HTTP 404 "no longer available" from Gemini: the model ID in `GEMINI_MODELS` has been retired. Update the list. A `GEMINI_MODELS` entry in a `.env` file overrides the code default.
- Very slow responses, then fallback to a later model: an earlier model in `GEMINI_MODELS` is timing out. Remove it or move it later.
- HTTP 429 from Gemini: free-tier quota; the client retries once and then moves to the next model.
- Narrative source shows "deterministic template": the model output failed number tracing three times, or the model was unavailable. This is intended fail-closed behaviour; see `guardrail_events`.
- Status `rejected` with "unit ... not recognised": supply a unit (mm, cm, m, in, ft for lengths; kN/m, N/m, t/m and similar for loads). Loads in kN or kN/m2 are rejected.
- `ModuleNotFoundError: app`: run uvicorn and pytest from the `backend` directory.
- Frontend not served: `frontend/` must sit next to `backend/`.

## Contributing

The repository contains no contribution guide or linter configuration. Observed conventions:

- Python with type annotations, `from __future__ import annotations`, module docstrings, Pydantic v2 models, and short functions.
- Each verifier rule is a single function with a clause ID; add new checks through the `@rule` decorator and add a mutation test.
- Add tests for any change to calculator, guardrails or pipeline behaviour, and run `python3 -m pytest -q` before submitting.
- Git history currently has a single commit ("first commit"); no branching strategy or commit message format is defined. A short imperative subject line is suggested.

## License

No license file is present in the repository. All rights are reserved by default until a license is added.

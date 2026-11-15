# SDC-V: Structural Design Copilot with Deterministic Verifier

SDC-V is a web application and JSON API that produces a draft reinforced-concrete (RCC) beam design to IS 456:2000 from either a structured form or a plain-English brief. A language model (Google Gemini) is used only to extract fields from the brief and to write the explanation of the result. Every engineering number is produced by a deterministic Python calculator, every pass or fail verdict is produced by a registry of clause-tagged rules, and any model-written narrative is rejected if it contains a number that is not present in the verified result. Every run is stored in a SQLite audit log and stamped as a draft that requires review by a licensed structural engineer.

Version: 0.2.0 (`APP_VERSION` in `backend/app/config.py`). Code edition: IS456:2000.

# Table of Contents

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

# Overview

## What problem it solves

Drafting a singly reinforced rectangular beam by hand involves many small calculations and checks (loads, moment, flexure, bar selection, shear, deflection, detailing) where a single wrong number is hard to spot. Using a language model to do this directly is unreliable because a model can state plausible but wrong numbers. SDC-V separates the two concerns. Code owns every number and every verdict. The model is confined to reading the brief and narrating a result that has already been verified, and its narrative is checked mechanically against that result.

## Who it is for

- Structural engineers and students who want a fast, checked first draft of a beam section and reinforcement.
- Developers and reviewers who want a reference for a guarded LLM pipeline in which the model never owns a number.

The tool does not replace engineering judgement. All output carries the stamp "DRAFT: requires review and sign-off by a licensed structural engineer. This output is not a certified design."

## Core capabilities

- Design of singly reinforced rectangular beams, simply supported or cantilever, under a uniformly distributed load, using the limit state method of IS 456:2000: loads, bending moment and shear, flexure, tension bar selection, shear reinforcement, deflection control and detailing.
- Two input paths: a structured form (`POST /api/design`) and a natural-language chat with optional images and a pasted attachment (`POST /api/chat`).
- 19 clause-tagged verifier rules, including two independent cross-checks of the calculator, and a deterministic reviser that enlarges the section (depth first, then width, in 25 mm steps) when a revisable rule fails.
- A what-if explorer that scans 51 nearby sections through the same calculator and rules, with no model call and no audit write.
- A number-trace output guardrail: every number in a model-written narrative must appear in the verified result, with up to three attempts and then a deterministic template.
- An audit log of every design run (SQLite), with filtering, statistics, CSV export, Markdown report export and a reviewer log entry.
- A reference knowledge base of 105 entries in 19 topics, and an expert-system view generated from the running code (facts, rules, meta-rules, module flow, endpoints).
- A browser interface with eight views, light and dark themes, a command palette and a chart viewer.
- A benchmark with pre-flight checks and metrics for the regex guards, and a 60-case end-to-end benchmark.

## System boundaries

In scope (enforced by `BeamInput` in `backend/app/schemas.py`):

- Span 0 to 15 m (cantilever length up to 6 m); width b 150 to 1000 mm; overall depth D 200 to 2000 mm, with D/b at most 4; nominal cover 20 to 100 mm and at least 100 mm less than D.
- Concrete grades M20, M25, M30, M35, M40; steel grades Fe250, Fe415, Fe500.
- Exposure: mild, moderate, severe, very severe, extreme.
- Dead load (excluding self-weight) and live load, each 0 to 500 kN/m, not both zero.

Detected and declined (out of scope): T and L beams and flanged sections, doubly reinforced beams, continuous beams, slabs, columns, footings and foundations, prestressed concrete, design codes other than IS 456:2000, seismic and ductile detailing (IS 13920), steel design (IS 800), walls, retaining structures and deep beams, and point loads.

Refused as unsafe requests: approving or certifying a design, reducing safety margins, removing structural elements, skipping inspections.

Not provided: user accounts, roles, multi-tenant isolation, Docker or CI configuration, a license file.

# Architecture

## High-level system architecture

The system has four layers.

1. Browser interface: static HTML, CSS and native ES modules in `frontend/`, with no build step and no third-party runtime dependency.
2. Optional Node proxy: `frontend/server.mjs` serves the static files and forwards `/api/*` to the backend. The backend can also serve the interface itself.
3. FastAPI backend: `backend/app/`, a JSON API plus a static file server, with a request middleware for token check, rate limit, security headers and request log.
4. Persistence and external services: a SQLite audit log in `backend/data/audit.db`, and the Google Gemini REST API (the only external service).

Request path for a chat design: browser, optional Node proxy, FastAPI route, `Pipeline.run_chat`, then in order: scope screen, injection flags, PII redaction, Gemini intake, number grounding, unit normalisation and range validation, calculator, verifier, reviser loop, report data, Gemini narrative with number trace (or template), server-side section sketch, audit write, JSON response.

## Backend architecture

- `main.py` builds the FastAPI app and instantiates one `AuditLog`, one `GeminiClient`, one `Pipeline` and one `RateLimiter` at import time. Each request that needs the pipeline calls `pipeline.with_model(model)`, which returns a new `Pipeline` bound to a per-request `GeminiClient` that tries the selected model first and then the other configured models.
- `pipeline.py` is the orchestrator. It owns the status vocabulary (`designed`, `needs_engineer`, `needs_info`, `rejected`, `out_of_scope`, `refused`, `error`), the calculator, verifier and reviser loop (`design_with_verification`), the `RunResult` response model and the per-stage trace.
- `guardrails/input.py` holds input handling: the `RawIntake` model, unit normalisation, range validation, scope and unsafe-request screening, injection pattern flags, PII redaction and number extraction for grounding.
- `guardrails/output.py` holds the number-trace check.
- `is456/` holds the calculator and the code tables. Both are pure Python with no I/O.
- `verifier.py` holds the rule registry. Each rule recomputes key quantities from the raw input with its own formulas, so a fault in the calculator is caught as a cross-check failure.
- `llm/` holds the Gemini client, the intake agent and the report writer.
- `audit.py`, `export.py`, `explore.py`, `scope.py`, `kb.py`, `system_model.py`, `report.py`, `sketch.py`, `reviser.py`, `schemas.py`, `security.py`, `config.py` hold the remaining logic (see Project Structure).

## Frontend architecture

- Vanilla JavaScript as native ES modules loaded from `frontend/app.js` (`<script type="module">`). There is no bundler, transpiler or package dependency.
- `chrome.js` owns the shell (header, sidebar, router, status bar, command palette, theme). Each view is one module that registers itself with the router. `result.js` renders a design result (verdict dashboard, checks, trace) for Form design, History and the Assistant.
- `theme.css` is the only place colours are defined. The interface colours deterministic output (calculator, verifier, reviser, audit) differently from language-model output (intake, narrative) and reserves green, amber and red for verdicts.
- Beam drawings (`beam.js`) are inline SVG rendered from numbers returned by the API. No engineering value is computed in the browser.
- Content Security Policy is `script-src 'self'`, so there are no inline scripts. The theme is applied before first paint by an external script (`theme-init.js`).

## Data layer

One SQLite file (`backend/data/audit.db`, created on first start) with one table, `runs`. See Database Schema. There is no ORM; `audit.py` uses the standard `sqlite3` module with one connection per call and a lock around writes.

## Integration points

- Gemini REST API: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` for intake, narrative and the live check; `GET .../v1beta/models?pageSize=200` to list models during the live check. Authentication is the `x-goog-api-key` header.
- Browser to backend: same-origin JSON over HTTP, through the Node proxy or served directly by FastAPI.

## External services used

- Google Gemini API (model calls). Text sent to it is redacted for email addresses and phone numbers first. Images attached to a chat are sent to it as inline data.
- No other external service. No telemetry, analytics or error-tracking service is configured.

## Design patterns used

- Pipeline with explicit stages and a status vocabulary.
- Rule registry: rules are plain functions registered with a decorator (`@rule`), which gives a single source for the verifier, the rule list API and the rules fingerprint.
- Protocol-based model client: `LLM.generate(system, user, json_mode, images)` is the only contract the pipeline needs, which is how tests substitute a scripted fake.
- Fail closed: if the model is unavailable, unparseable or untraceable, the result is an explicit error status or a deterministic template, never a guessed value.
- Allowlists over blocklists for static files and model identifiers.
- Per-request object graph: `with_model` creates a fresh `Pipeline` and `GeminiClient`, so per-request state (trace, attempts, last model) is not shared between requests.
- Single source of truth for scope: `scope.py` reads limits from the `BeamInput` schema and labels from the guard patterns, so the scope view cannot drift from validation.

## Diagrams explained in text

Design flow, left to right:

- Input: form values or a chat brief (with optional attachment and images).
- Guardrails: scope screen, injection flags, PII redaction, grounding, unit and range validation.
- Calculator: produces a `Design` (all numbers).
- Verifier: runs 19 rules over the input and design.
- Reviser: if an error-level rule that resizing can fix fails, enlarge the section by 25 mm and loop back to the calculator, up to 8 times. If a failing rule cannot be fixed by resizing, stop with status `needs_engineer`.
- Report data: pre-formatted strings from the verified result.
- Narrative: Gemini writes text from the report data; the number trace compares every number to the report data; after three rejected attempts a template is used.
- Audit: the full `RunResult` is stored with the code edition and rules fingerprint.

Module trust boundary: the model sits at two points only (intake and narrative). Between them everything is code. The audit write and the final response contain only values that came from code.

# Project Structure

## Root Directory

- `README.md` — This document.
- `.gitignore` — Excludes secrets (`.env`, `.env.*` except `.env.example`), local databases (`*.db`, `*.sqlite3`), Python caches and virtual environments, tooling state directories (`.claude/`, `.claude-flow/`, `.swarm/`, `.agents/`, `.codex/`), logs, benchmark outputs (`benchmark/results/`, `benchmark/*_results.*`) and the local notes file `LLM_addition.md`.
- `.env` — Optional, untracked. A repository-root environment file read by `config.py` after `backend/.env`.
- `SDC-V.docx`, `SDC-V.pdf`, `SDC-V_v2.docx`, `Structural_Design_Copilot.docx` — Project report documents. They are not used at runtime. The v2 report predates the current frontend and the guard benchmark.
- `LLM_addition.md` — Untracked local planning notes (ignored by git). Not part of the product.
- `.claude-flow/` — Untracked tooling state. Not part of the product.

## /backend

- `requirements.txt` — Python dependencies with lower bounds only: `fastapi>=0.110`, `uvicorn>=0.29`, `pydantic>=2.6`, `httpx>=0.27`, `pytest>=8.0`. There is no lock file.
- `.env.example` — Tracked template for `backend/.env`.
- `data/audit.db` — The SQLite audit log, created on first start. Untracked.

## /backend/app

- `__init__.py` — Package marker.
- `main.py` — FastAPI application, request and response models for the API, the request middleware, all routes, and the static file routes (`/` and `/static/{name}`). Configures logging.
- `config.py` — Loads `.env` files, defines the model list, timeouts, rate limit, API token accessor, data directory and the reviser and writer limits.
- `pipeline.py` — Orchestration. Defines `RunResult`, `TraceStep`, `LLMAttempt`, the `Pipeline` class (`run_structured`, `run_chat`, `with_model`), the verification loop `design_with_verification` and `tool_versions`.
- `schemas.py` — Pydantic models shared across the pipeline: `BeamInput` (validated, unit-normalised input and the supported limits), `CheckResult`, `BarArrangement`, `Design` (every calculator output; includes the presentation constant `eps_cu`).
- `verifier.py` — The rule registry: 19 rules registered with `@rule`, `RULE_META`, `run_rules` and `rules_fingerprint` (a 12-character SHA-256 prefix over rule IDs and clauses).
- `reviser.py` — Deterministic section reviser: depth in 25 mm steps while D is at most 3b and 2000 mm, then width up to 1000 mm.
- `report.py` — `ReportData` (pre-formatted strings), the draft `STAMP`, `build_report_data`, the deterministic `template_narrative` and `bar_text`.
- `sketch.py` — Server-side SVG cross-section (`section_svg`) included in the response for reports and exports. The browser UI draws its own SVG from numbers.
- `explore.py` — The what-if explorer. No model, no audit write.
- `export.py` — Markdown report for a stored run, and CSV export of run lists with spreadsheet formula-injection protection.
- `scope.py` — Builds the supported-scope description from the `BeamInput` schema, the guard pattern labels, fixed assumptions and reviser settings.
- `security.py` — Client IP resolution, the sliding-window `RateLimiter`, constant-time token comparison, and the security header set.
- `audit.py` — The SQLite audit log: save, search, get, review, stats and a health ping.
- `kb.py` — The reference knowledge base: 105 entries in 19 topics, served by `GET /api/kb`. Entries carry an `implemented` flag (shown as "in calculator" in the UI).
- `system_model.py` — Describes the system as a knowledge-based system (facts, derivation rules, verifier rules, guardrail rules, meta-rules, modules, edges, cognitive mapping, endpoints). Facts and verifier rules are read from live code. Served by `GET /api/system`.

## /backend/app/guardrails

- `__init__.py` — Package marker.
- `input.py` — `Quantity` and `RawIntake`; unit conversion tables; `normalise` (units, ranges, grade parsing, support and exposure aliases; returns beam, missing fields, errors, out-of-scope notes and conversions); `screen_scope` (out-of-scope and unsafe-request patterns, negation-aware); `detect_injection` (logging-only pattern flags); `redact` (email and phone); `numbers_in` (for grounding).
- `output.py` — `trace_numbers`: returns the numbers in a narrative that do not occur in the strings of the report data.

## /backend/app/is456

- `__init__.py` — Package marker.
- `calculator.py` — `design_beam`: loads, moment and shear, effective depth, flexure (Annex G), bar selection, shear reinforcement and stirrup spacing, deflection control, detailing. Pure Python, no I/O.
- `tables.py` — IS 456:2000 constants and tables with clause references: code edition, unit weight, load factor, stirrup assumptions, bar diameters, aggregate size, limiting neutral-axis ratios, minimum cover and grade by exposure, maximum shear stress by grade, maximum bar spacing by steel grade, and `EPS_CU` (0.0035, used only for presentation).

## /backend/app/llm

- `__init__.py` — Package marker.
- `gemini.py` — `GeminiClient`: REST client with ordered model fallback, up to two attempts per model, retry on HTTP 429, 500 and 503 and on network errors, no retry after a timeout, temperature 0, 8192 output tokens, a per-call timeout and a total time budget, a bounded list of per-call attempts, a live `probe`, and `remote_models`. Also `LLM` (protocol), `LLMError` and `parse_json`.
- `intake.py` — The intake agent: a system prompt and `run_intake`, which asks the model for JSON (intent, fields, image transcription), validates it, and retries once on parse failure.
- `writer.py` — The writer system prompt and `write_report`: up to three attempts, each checked by the number trace and for the draft stamp, then the template fallback.

## /backend/tests

- `__init__.py`, `conftest.py` — Test package; shared `base_input` fixture and a scripted `FakeLLM`.
- `test_calculator_golden.py` — 25 tests: calculator against IS 456 table values and SP 16-style closed forms, with a 2% tolerance.
- `test_verifier_mutation.py` — 14 tests: faults injected into the calculator output must be flagged by the verifier.
- `test_guardrails.py` — 23 tests: normalisation, units, ranges, scope screen, unsafe requests, injection flags, redaction.
- `test_knowledge_system.py` — 10 tests: knowledge base and expert-system payloads.
- `test_pipeline_api.py` — 12 tests: pipeline statuses and API routes with a scripted model.
- `test_v2_features.py` — 17 tests: model fallback and timeout behaviour (mocked HTTP), audit redaction, filters and statistics, CSV safety, report export, scope, explorer, token auth, rate limiting, security headers, static allowlist, deep health.
- `test_guard_cases.py` — 218 parametrised tests: every labelled case in `benchmark/guard_cases.jsonl` and the guard-relevant cases in `benchmark/cases.jsonl`, plus negation and unsafe-wording regression tests.
- `test_benchmark_metrics.py` — 13 tests: the benchmark metrics and the pre-flight checks.

## /benchmark

- `cases.jsonl` — 60 end-to-end cases: golden (20), needs_revision (8), incomplete (10), invalid (8), out_of_scope (6), injection (8).
- `generate_cases.py` — Regenerates `cases.jsonl`.
- `run_benchmark.py` — Runs the pre-flight checks, the end-to-end cases and the guard metrics. Options: `--llm`, `--baseline`, `--guards-only`, `--no-checks`.
- `guard_cases.jsonl` — Labelled texts for the regex guards, including benign briefs that contain trigger words. Entries marked `known_gap` are attacks the regexes are not expected to catch.
- `generate_guard_cases.py` — Regenerates `guard_cases.jsonl`.
- `guard_eval.py` — Runs `screen_scope` and `detect_injection` over the labelled cases.
- `metrics.py` — Confusion matrix, safety and usability rates, false allows and false blocks, MCC, seeded bootstrap intervals, trivial baselines.
- `checks.py` — Pre-flight checks: label leakage into model-visible text, empty or oversized inputs, duplicate cases, missing fields, one-sided case sets.

## /frontend

- `index.html` — Page shell: header, sidebar container, eight view containers, status bar, token dialog, command palette dialog.
- `package.json` — npm manifest. `npm start` runs `node server.mjs`. No dependencies. Requires Node 18 or later.
- `server.mjs` — Node HTTP server: serves `index.html` and an explicit allowlist of assets, proxies `/api/*` to `BACKEND_URL` (overwriting `X-Forwarded-For`), and adds security headers to the pages it serves.
- `app.js` — Entry point; imports every module, installs tooltips, the chrome and the chart viewer, and shows the view named by the URL hash.
- `core.js` — DOM helpers, HTML escaping, storage wrappers, the API client (token header, 401 retry, error mapping), shared state and an event bus.
- `fmt.js` — Presentation formatting: engineering notation (N/mm², kN/m³, ×, arrows, minus sign), verdict labels, a parser that turns stored raw model errors into short readable text, count-up animation.
- `ui.js` — Shared components: icons, panel, pills, origin tags, stat tiles, data table (sticky header, sorting, expandable rows), skeleton, empty and error states, rule check cells, utilisation bars, title block, console view, tooltips.
- `beam.js` — Inline SVG drawings from returned numbers: cross-section, elevation, shear force and bending moment, strain diagram, and the input-only preview.
- `chrome.js` — Theme control, sidebar (collapse, drawer), router, health loading and model selector, status bar, command palette.
- `result.js` — Rendering of a design result: verdict dashboard, rule grid, utilisation, attention list, design values, drawings, revision list, narrative, trace waterfall, model attempt chain, actions, review form.
- `home.js`, `chat.js`, `design.js`, `explore.js`, `kb.js`, `system.js`, `history.js`, `scope.js` — One module per view.
- `viewer.js` — Chart viewer: any beam drawing or knowledge-base chart opens large with zoom, pan and SVG or PNG download.
- `fixture.js` — A precomputed example for the Home page, generated once from the real calculator and verifier. Nothing is run or logged when Home plays it.
- `kbcharts.js` — Charts for knowledge-base entries (classic script exposing `window.kbChart`).
- `theme.css` — Design tokens (colours, radii, spacing) for light and dark themes.
- `theme-init.js` — Applies the saved or system theme before first paint.
- `styles.css` — Components and layout; print stylesheet.

# Installation

## System requirements

- Linux, macOS or Windows.
- Python 3.10 or later (the code uses PEP 604 union syntax such as `X | None`). The project was developed and tested on Python 3.14 with pydantic 2.13.
- Node.js 18 or later, only if you run the frontend through `npm start`. The backend serves the same interface on its own.
- A Gemini API key, only for natural-language intake and model-written narratives. The structured form, the explorer and template reports work without one.

## Package manager requirements

- `pip` for the backend. Dependencies are listed in `backend/requirements.txt` with lower bounds and no lock file.
- `npm` (or plain `node`) for the frontend. There are no frontend packages to install.

## Step-by-step setup

Create a virtual environment and install the backend dependencies:

```
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optionally create a `.env` file (see Configuration). Without a key the application still starts; chat requests then return status `error` and the form path returns template narratives.

No database setup is needed. The SQLite file and its table are created on first start.

# Configuration

## Environment variables

Read by the backend (`backend/app/config.py`):

- `GEMINI_API_KEY` — Gemini API key. Default: empty, which disables natural-language intake and model-written narratives.
- `LLM_TIMEOUT_S` — Timeout for one Gemini call, in seconds. Default: 25.
- `LLM_BUDGET_S` — Total wall-clock budget for one `generate()` call across all models and retries, in seconds. Default: 60.
- `SDCV_API_TOKEN` — If set, every `/api/*` route except `/api/health` requires this token. Default: unset (no authentication).
- `RATE_LIMIT_PER_MIN` — Requests per minute per client and per route for `POST /api/chat`, `/api/design` and `/api/explore`. Default: 30. A value of 0 disables the limit.
- `SDCV_DATA_DIR` — Directory for `audit.db`. Default: `backend/data`. Used to point tests or experiments at a throwaway database.

Optional local-model settings (all unset by default, which leaves Gemini reading briefs and images). See `training/README.md`:

- `SDCV_INTAKE_BACKEND` — `gemini` (default) or `local`. `local` uses a fine-tuned Qwen for intake.
- `SDCV_LOCAL_MODEL`, `SDCV_LOCAL_ADAPTER`, `SDCV_LOCAL_4BIT` — the base model, its LoRA adapter folder, and 4-bit loading.
- `SDCV_VISION_BACKEND` — `gemini`, `local` or empty. When set, an attached image is first transcribed to text by that model, then read by the intake model. Defaults to `gemini` when intake is `local`.
- `SDCV_VISION_MODEL` — the local vision model (default `Qwen/Qwen2.5-VL-3B-Instruct`).

Read by the Node server (`frontend/server.mjs`):

- `PORT` — Listening port. Default: 3000.
- `HOST` — Listening address. Default: 127.0.0.1.
- `BACKEND_URL` — Backend origin to proxy `/api/*` to. Default: `http://127.0.0.1:8000`.

## Configuration files

- `backend/.env` and the repository-root `.env`: simple `KEY=value` lines; blank lines and lines starting with `#` are ignored; surrounding quotes are stripped. `backend/.env` is read first, then the root `.env`.
- `backend/.env.example` is the tracked template.

## Precedence and overriding

Values are applied with "set if not already set". A real environment variable wins over `backend/.env`, which wins over the root `.env`. An environment variable that is set but empty still counts as set, so `GEMINI_API_KEY=` on the command line disables the model even if a `.env` file contains a key.

## Settings that are not environment variables

These are constants in code and require an edit and a restart:

- The selectable models (`MODEL_OPTIONS` in `config.py`): `gemini-3.5-flash-lite` (default), `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.8-flash`, `gemini-3-flash-preview`. The selected model is chosen per request in the interface; the others are the fallback order.
- `MAX_REVISER_ITERATIONS` = 8 and `MAX_WRITER_ATTEMPTS` = 3.
- The static file allowlists in `backend/app/main.py` and `frontend/server.mjs`.

## Secrets handling

- The API key and token are read from the environment or from untracked `.env` files. `.gitignore` excludes `.env` and `.env.*` except `.env.example`.
- The key is sent only in the `x-goog-api-key` header to the Gemini API. It is never returned by any endpoint, and `/api/health` reports only whether a key is configured.
- The API token entered in the browser is kept in `sessionStorage` for that tab only.

# Usage

## Start the backend

```
cd backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The backend serves the interface and the API from one origin, provided the `frontend/` directory sits next to `backend/`.

## Start the frontend through Node (optional)

```
cd frontend
npm start
```

Open `http://127.0.0.1:3000/`. To change the port or the backend address:

```
PORT=4000 npm start
BACKEND_URL=http://127.0.0.1:9000 npm start
```

## Development mode

```
cd backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend files are served with `Cache-Control: no-cache`, so a browser refresh picks up edits. A new frontend file must be added to the allowlist in `backend/app/main.py` and in `frontend/server.mjs`, otherwise `/static/<name>` returns 404.

## Production mode

There is no production-specific configuration in the repository. Use a single worker (the rate limiter and the live-check cache are in memory) and place a reverse proxy with TLS in front:

```
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

See Deployment.

## Command line tools

```
cd backend && python3 -m pytest -q
cd benchmark && python3 run_benchmark.py
cd benchmark && python3 run_benchmark.py --guards-only
cd benchmark && python3 run_benchmark.py --llm
cd benchmark && python3 run_benchmark.py --baseline
cd benchmark && python3 generate_cases.py
cd benchmark && python3 generate_guard_cases.py
```

## API usage examples

Structured design (no model needed for intake):

```
curl -s -X POST http://127.0.0.1:8000/api/design \
  -H 'Content-Type: application/json' \
  -d '{"span":{"value":6,"unit":"m"},"support":"simply_supported","b":{"value":300,"unit":"mm"},"D":{"value":550,"unit":"mm"},"cover":{"value":30,"unit":"mm"},"fck":25,"fy":500,"dead_load":{"value":15,"unit":"kN/m"},"live_load":{"value":12,"unit":"kN/m"},"exposure":"moderate"}'
```

Natural-language chat (needs `GEMINI_API_KEY`):

```
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","text":"Simply supported beam, 6 m span, 300 x 550 mm, cover 30 mm, M25 concrete, Fe500 steel, dead load 15 kN/m, live load 12 kN/m, moderate exposure."}]}'
```

Choose a model for one request:

```
curl -s -X POST 'http://127.0.0.1:8000/api/design?model=gemini-3.5-flash' -H 'Content-Type: application/json' -d '{...}'
```

Section explorer, history, report and review:

```
curl -s -X POST http://127.0.0.1:8000/api/explore -H 'Content-Type: application/json' -d '{...same body as /api/design...}'
curl -s 'http://127.0.0.1:8000/api/runs?status=designed&limit=10'
curl -o report.md http://127.0.0.1:8000/api/runs/RUN_ID/report.md
curl -s -X POST http://127.0.0.1:8000/api/runs/RUN_ID/review -H 'Content-Type: application/json' -d '{"reviewer":"A. Engineer, reg. 1234","note":"checked"}'
```

When `SDCV_API_TOKEN` is set, add a header to every request except `/api/health`:

```
-H 'Authorization: Bearer YOUR_TOKEN'
```

# API Documentation

All routes are on one origin. Responses under `/api/` carry `Cache-Control: no-store` and the security headers. Domain outcomes (declined, rejected, needs more information, model unavailable) are returned with HTTP 200 and a `status` field; HTTP error codes are reserved for transport, validation and authorisation problems.

Common errors on every `/api/` route:

- 401 `{"detail": "missing or invalid API token"}` with `WWW-Authenticate: Bearer`, when a token is configured and missing or wrong (not applied to `/api/health`). The token may be sent as `Authorization: Bearer <token>` or `X-API-Key: <token>`.
- 422 Pydantic validation error, for a malformed body or query parameter (for example a `model` value that is not one of the configured models, or an out-of-range `limit`).
- 429 `{"detail": "rate limit exceeded; retry in <n>s"}` with `Retry-After`, for `POST /api/chat`, `/api/design` and `/api/explore` when the per-client, per-route limit is exceeded.

## Result statuses

- `designed`: all error-level rules pass (the section may have been revised).
- `needs_engineer`: an error-level rule that resizing cannot fix failed, the reviser reached its limit, or the section reached size limits.
- `needs_info`: required fields are missing; `question` and `missing` are set.
- `rejected`: input failed unit or range validation; `errors` lists the reasons.
- `out_of_scope`: a feature outside the supported scope was detected.
- `refused`: an unsafe request was detected.
- `error`: natural-language intake could not run (no key) or the model could not be reached or returned unusable output.

## GET /api/health

- Query: `deep` (boolean, default false), `model` (one of the configured model identifiers).
- Response: `ok`, `llm_configured`, `models`, `model_options` (each with `id`, `label`, `note`), `default_model`, `code_edition`, `auth_required`, `rate_limit_per_min`, `versions` (`app`, `python`, `pydantic`, `code_edition`, `rules_fingerprint`), `db_ok`.
- With `deep=true`, also `llm`: `probe` (`ok`, `model`, `latency_ms`, `skipped` per-model errors, or `error`), `unavailable_models` (configured models not listed by the API, or null if the lookup failed) and `cached`. The live check makes one real model call and is cached for 60 seconds per model.
- Status codes: 200. Does not require the token.

## GET /api/rules

- Response: a list of verifier rules, each with `rule_id`, `title`, `clause`, `severity` (`error` or `warning`) and `revisable`.

## GET /api/scope

- Response: `code`, `supported`, `limits` (bounds read from `BeamInput`, allowed grades, supports and exposures, cantilever maximum, maximum D/b), `out_of_scope`, `refused`, `fixed_assumptions`, `reviser`, `rule_count`, `limits_note`.

## GET /api/kb

- Response: `topics` (each with `id`, `label`, `count`), `entries` (each with `id`, `topic`, `title`, `summary`, `points`, `formulas`, `tags`, `clause`, `implemented`), `count`, `note`.

## GET /api/system

- Response: `summary` (counts and fingerprint), `facts`, `derivation_rules`, `verifier_rules`, `guardrail_rules`, `meta_rules`, `layers`, `nodes`, `edges`, `main_path`, `cognitive`, `interface`.

## POST /api/design

- Query: `model` (optional).
- Body (`RawIntake`): `span`, `b`, `D`, `cover`, `dead_load`, `live_load` as `{"value": number, "unit": string}`; `support` string; `fck`, `fy` number or string such as "M25"; `exposure` string. Missing fields produce `needs_info`.
- Response (`RunResult`): `run_id`, `status`, `mode` (`structured`), `message`, `question`, `missing`, `errors`, `out_of_scope`, `conversions`, `original_input`, `final_input`, `design` (all calculator values, including `eps_cu`), `checks` (each with `rule_id`, `title`, `clause`, `passed`, `value`, `limit`, `op`, `unit`, `decimals`, `severity`, `revisable`, `message`), `iterations`, `report` (pre-formatted strings), `narrative`, `narrative_source` (`llm` or `template`), `image_text`, `sketch_svg`, `guardrail_events`, `llm_model`, `stamp`, `trace` (each stage with `stage`, `origin`, `ms`, `status`) and `llm_attempts` (each with `model`, `outcome`, `ms`).
- The run is written to the audit log. The narrative uses Gemini when a key is configured, otherwise the template.
- Status codes: 200, 401, 422, 429.

## POST /api/chat

- Query: `model` (optional).
- Body: `messages` (1 to 20 items, each `role` of `user` or `assistant` and `text` up to 8000 characters), `attachment_text` (up to 20000 characters, treated as data), `images` (up to 3; each `mime` of `image/png`, `image/jpeg` or `image/webp` and base64 `data` up to 5,000,000 characters whose leading bytes must match the declared type).
- Response: `RunResult` with `mode` `chat`.
- Status codes: 200, 401, 422, 429. A missing key or an unreachable model is returned as 200 with status `error`.

## POST /api/explore

- Body: same as `POST /api/design`.
- Response: `status` (`ok`, `needs_info`, `rejected`, `out_of_scope`), `base` (`b`, `D`), `rows` (51 candidate sections: width b minus 50, b, b plus 50 mm, clamped to 150 to 1000 mm, and depth D minus 100 to D plus 300 mm in 25 mm steps; each with `b`, `D`, `d`, `ok`, `failed`, `warnings`, `ast_req`, `ast_prov`, `pt`, `bars`, `sv`, `concrete_area_mm2`, `self_weight`, `Mu`, `ld_actual`, `ld_allow`), `lightest_passing`, `passing`, `scanned`, `conversions`, `note`.
- No model call and no audit write.

## GET /api/runs

- Query: `limit` (1 to 200, default 50), `offset` (default 0), `status`, `mode` (`chat` or `structured`), `q` (up to 80 characters, matched against run ID, summary and reviewer), `reviewed` (boolean).
- Response: a list of `id`, `created_at`, `status`, `mode`, `summary`, `reviewer`, `reviewed_at`, newest first. Header `X-Total-Count` carries the total number of matches.

## GET /api/runs.csv

- Query: same filters as `/api/runs` without paging; up to 5000 rows.
- Response: CSV with a download filename. Cells that start with `=`, `+`, `-` or `@` are prefixed with an apostrophe.

## GET /api/stats

- Response: `total`, `by_status`, `by_mode`, `reviewed`, `last_24h`, `models` (runs per model), `narrative_source` (runs per source).

## GET /api/runs/{run_id}

- Response: `id`, `created_at`, `status`, `mode`, `summary`, `record` (the stored `result`, `versions`, `llm_model`, and for structured runs `raw_input`, for chat runs the redacted `messages`, `attachment_chars`, `image_count` and `intake`), `reviewer`, `reviewed_at`, `review_note`.
- Status codes: 200, 401, 404 `{"detail": "run not found"}`.

## GET /api/runs/{run_id}/report.md

- Response: a Markdown report built from the stored, verified result, as a download.
- Status codes: 200, 401, 404.

## POST /api/runs/{run_id}/review

- Body: `reviewer` (2 to 120 characters), `note` (up to 2000 characters, optional).
- Response: `{"ok": true}`. This records a log entry; it is not a certification.
- Status codes: 200, 401, 404, 422.

## GET / and GET /static/{name}

- `/` returns `frontend/index.html`. `/static/{name}` returns one of an explicit list of frontend files (single path segment only); any other name returns 404 `{"detail": "not found"}`. These routes are not covered by the API token.

# Data Flow Explanation

## How data enters the system

- Form: the browser posts a `RawIntake` to `/api/design` or `/api/explore`.
- Chat: the browser posts messages, an optional pasted attachment and up to three images to `/api/chat`. Images are resized and re-encoded as JPEG in the browser before upload.

## How it is processed (chat path)

1. Scope screen on the user's own words (not the attachment). An out-of-scope feature returns `out_of_scope`; an unsafe request returns `refused`. No model is called.
2. Injection pattern flags on the brief and the attachment are written to `guardrail_events` and logged. They do not block the request.
3. If no key is configured, the result is `error`.
4. Email addresses and phone numbers are redacted from the transcript and the attachment.
5. Intake: Gemini returns JSON with an intent, extracted fields and, for images, a verbatim transcription. The prompt tells the model to extract only, to treat attachments and images as data, and to leave unknown fields null. Output is parsed and validated, with one retry.
6. Intent handling: `unsafe_request` returns `refused`; `out_of_scope` or `not_a_beam_brief` returns `out_of_scope`.
7. Grounding: each extracted number (span, b, D, cover, dead load, live load, fck, fy) must appear in the brief, the attachment or the image transcription. A number that does not is dropped and the field becomes missing. If the model reports the loads as factored, the result is `needs_info`.
8. Normalisation and validation: units are converted to mm, m and kN/m (conversions are recorded), grades and aliases are parsed, ranges are checked. The result is a validated `BeamInput`, or `needs_info`, `rejected` or `out_of_scope`.
9. Design loop: the calculator produces a `Design`, the verifier runs 19 rules, and the reviser enlarges the section while a revisable error persists, up to 8 times.
10. Report data and narrative: report strings are built from the verified result. Gemini writes the narrative with up to three attempts, each checked by the number trace and for the draft stamp; otherwise the template is used.
11. Sketch, audit write, response.

The form path (`/api/design`) starts at step 8. Its narrative still uses Gemini if a key is configured.

## Where it is stored

The full `RunResult` and the tool versions are stored as JSON in the `runs` table. Chat messages are stored redacted; the attachment is not stored (only its length); images are not stored (only their count). Structured form values are stored as submitted.

## How it is returned

The response is the `RunResult` JSON. The browser renders every number from it. The report endpoint rebuilds a Markdown report from the stored record, not from the model.

# Database Schema

SQLite, file `backend/data/audit.db` (or `SDCV_DATA_DIR`). Created with `CREATE TABLE IF NOT EXISTS` on start. There is no migration tool.

## Table runs

- `id` TEXT, primary key. A 12-character hexadecimal run ID.
- `created_at` TEXT, not null. UTC ISO 8601 timestamp to the second.
- `status` TEXT, not null. One of the result statuses.
- `mode` TEXT, not null. `chat` or `structured`.
- `summary` TEXT. A one-line description, for example the support, span, grades and section with the outcome.
- `record` TEXT, not null. JSON: `result` (the `RunResult`, including `trace` and `llm_attempts` for runs made after those fields were added), `versions` (`app`, `python`, `pydantic`, `code_edition`, `rules_fingerprint`), `llm_model`, and the mode-specific fields described under `GET /api/runs/{run_id}`.
- `reviewer` TEXT, `reviewed_at` TEXT, `review_note` TEXT. Set by the review endpoint.

## Indexes and constraints

- Primary key on `id`. `INSERT OR REPLACE` is used on save.
- `idx_runs_created` on `created_at` descending.
- `idx_runs_status` on `status`.
- No foreign keys. Statistics use SQLite `json_extract` over `record`, which scans the table.

# Testing

## How to run tests

```
cd backend
python3 -m pytest -q
```

The suite needs no network and no key. To keep it away from the real audit log and the model, set a throwaway data directory and an empty key:

```
SDCV_DATA_DIR=$(mktemp -d) GEMINI_API_KEY= python3 -m pytest -q
```

The suite currently reports 332 passing tests (25 calculator, 14 verifier mutation, 23 guardrails, 10 knowledge system, 12 pipeline and API, 17 v2 features, 218 guard cases, 13 benchmark tooling).

## Test structure

- `conftest.py` supplies a `base_input` fixture and a scripted `FakeLLM` implementing the `LLM` protocol, so pipeline tests control exactly what the model "returns", including hallucinated numbers.
- Calculator tests compare against IS 456 table values and SP 16-style closed forms.
- Mutation tests perturb the calculator output and require the verifier to flag the fault.
- API tests use FastAPI's `TestClient`; Gemini HTTP calls are mocked for the client tests.
- Guard tests are driven by the labelled files in `benchmark/`.

## Benchmark

```
cd benchmark
python3 run_benchmark.py
```

It prints the pre-flight checks on both case files, runs the structured and deterministic cases, and reports the regex guards with a confusion matrix, safety and usability rates, MCC with a bootstrap interval and trivial baselines. Chat cases that need the model are counted as skipped without a key (18 of 60: the 10 incomplete and 8 injection cases). `--llm` runs them through Gemini; `--baseline` compares plain Gemini against the verified Ast on golden cases.

## Coverage notes

- No coverage tool is configured.
- The guard metrics are measured on a small set that the patterns were tuned on, so they describe regression behaviour, not expected real-world accuracy.

## Missing tests

- No automated frontend or end-to-end browser tests are committed.
- No test calls the live Gemini API; model behaviour is covered only through mocks and the optional benchmark.
- The Node server (`server.mjs`) has no tests.
- No concurrency, load or long-running tests.
- The rate limiter and the audit log are tested functionally, not under contention.

# Deployment

## What exists

The repository contains no Dockerfile, compose file, process-supervisor configuration, CI/CD workflow or infrastructure code. Deployment is manual.

## Production deployment steps

1. Install Python and the dependencies on the host (see Installation). Pin the versions you test with, because `requirements.txt` has lower bounds only.
2. Provide `GEMINI_API_KEY`, `SDCV_API_TOKEN` and optionally `RATE_LIMIT_PER_MIN` through the process environment rather than a file.
3. Run one uvicorn worker bound to loopback: `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`. Supervise it with your platform's process manager.
4. Put a reverse proxy with TLS in front. The application has no TLS and no user accounts. The backend takes the client address from the socket, or from the first `X-Forwarded-For` entry only when the socket peer is a loopback address, so run the proxy on the same host or the rate limiter will see one client.
5. Optionally run `frontend/server.mjs` (Node) as the public entry point, with `BACKEND_URL` pointing at the backend. It overwrites `X-Forwarded-For` with the real client address.
6. Back up `backend/data/audit.db` (or `SDCV_DATA_DIR`). It is the only persistent state.

## Environment separation

There is no named environment concept. Separate environments by using different environment variables and different `SDCV_DATA_DIR` values. Use a throwaway data directory for tests.

## Scaling considerations

- Run a single process. The rate limiter, the live-check cache and the per-process model client are in memory, so multiple workers would each keep their own counters.
- SQLite with one connection per call and a write lock is suitable for a single host. A shared database would need a different `AuditLog` implementation.
- Model latency, not computation, dominates request time.

# Logging and Monitoring

## Logging system

- Python `logging`, configured in `main.py` with `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")`, written to standard error.
- Logger `sdcv.http`: one line per API request: method, path, status, duration in milliseconds and client address.
- Logger `sdcv.llm`: an INFO line for each successful model call (model, milliseconds) and a WARNING with the per-model errors when every model fails.

## Log levels

INFO and above are emitted. There is no configuration for the level, no structured (JSON) logging and no log rotation.

## Error tracking and observability

- No error-tracking service, metrics endpoint or tracing integration.
- Each run stores a per-stage trace (stage, origin deterministic or language model, milliseconds, status) and the model attempts (model, outcome, milliseconds) in the audit record. The interface shows them for a run, and shows a status bar with backend, key, database, edition, rules fingerprint, selected model, last run time and rate limit.
- `GET /api/health` reports versions, key presence, database reachability and, with `deep=true`, a live model check.
- `GET /api/stats` aggregates runs by status, mode, model and narrative source.

# Security Considerations

## Authentication

An optional single shared token (`SDCV_API_TOKEN`). When set, every `/api/*` route except `/api/health` requires it as a bearer token or an `X-API-Key` header, compared in constant time. When unset, the API is open. The static routes (`/` and `/static/*`) are never protected.

## Authorization

None. There are no users or roles. Any client with the token (or any client, if no token is set) can list and read every run, export the log and log a review. The review endpoint records a name and a note; it does not verify identity and is not a certification.

## Input validation

- Pydantic validation on every request body and query parameter, with explicit length limits on chat messages, attachment text and images.
- Images must match their declared type by leading bytes and are limited in size and number.
- Engineering inputs pass unit normalisation and range validation (`BeamInput`) before any calculation.
- Model identifiers are validated against the configured list.
- Static files are served from allowlists with single-segment names, which blocks path traversal.
- CSV export neutralises spreadsheet formula injection.

## Prompt-injection and output controls

- The scope screen and unsafe-request screen run on the user's own words before any model call.
- Attachments and image text are labelled as data in the intake prompt. Regex injection flags are logged but do not block.
- Extracted numbers must be grounded in the user's text, attachment or image transcription.
- Narratives are checked by the number trace and fall back to a template.
- The model never produces a value used in a calculation or a verdict.

## Rate limiting

A sliding window of 60 seconds per client address and route for `POST /api/chat`, `/api/design` and `/api/explore`, default 30 per minute, in process memory (idle entries are pruned when more than 5000 keys accumulate). Over the limit returns 429 with `Retry-After`.

## Secrets management

Environment variables or untracked `.env` files; see Configuration. Nothing in the repository stores a secret. Email addresses and phone numbers are redacted before text is sent to the model and before chat messages are stored.

## Response headers

The backend sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin` and a Content-Security-Policy of `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'`. The Node server sets a subset of these on the pages it serves (nosniff, frame denial, referrer policy and the same Content-Security-Policy).

## Known vulnerabilities and risks

- No authentication by default, and no per-user access control when a token is set.
- No TLS in the application; it must be provided by a proxy.
- The Content-Security-Policy allows inline styles (`'unsafe-inline'` for styles) because the interface sets some styles from script.
- Redaction covers only email addresses and phone numbers. Other personal data in a brief or an image would be sent to the model provider.
- Images attached to a chat are sent to Google. They are not stored locally.
- Structured form values are stored in the audit log as submitted.
- Dependencies are not pinned and are not scanned.
- The injection detector is a list of regular expressions and can be bypassed by paraphrase; it only logs. The scope and unsafe-request screens can likewise be bypassed by paraphrase, in which case the model-side intent check and the deterministic validation are the remaining controls.

# Performance Considerations

## Bottlenecks

- Gemini latency. In development tests a single call took roughly 1.5 to 5 seconds, depending on the model, and models can return 503 or time out. A chat design makes one intake call and at least one narrative call (up to three).
- The calculator and verifier are pure computation; the per-stage trace shows well under a millisecond for a typical beam on the development machine.

## Time bounds

- Each model call times out at `LLM_TIMEOUT_S` (default 25 s). Each `generate()` call, across all models and retries, is limited to `LLM_BUDGET_S` (default 60 s). A request that makes several model calls can take longer than one budget. The Node proxy times out upstream requests at 300 seconds.
- A model that times out is skipped, not retried; models that return 429, 500 or 503 get one retry.

## Caching

- The live model check is cached for 60 seconds per model so polling cannot spend quota.
- Frontend files are served with `Cache-Control: no-cache`; API responses with `no-store`.
- No result cache. Identical designs are recomputed and re-logged.

## Optimisation notes and scalability

- The explorer evaluates 51 sections in one request with no model call.
- `GET /api/stats` uses `json_extract` over every row, so it grows linearly with the log.
- The CSV export is capped at 5000 rows. History is paged.
- Single process only (see Deployment).

# Limitations

- Scope is narrow: singly reinforced rectangular beams, simply supported or cantilever, UDL only, IS 456:2000 only. Anything else is declined, not approximated.
- The output is a draft. The tool does not certify, approve or sign off anything.
- Some IS 456 data is hand-entered or fitted: the shear strength factor tau_c uses a closed-form fit of Table 19, the deflection modification factor uses an analytic fit of Figure 4, and the code tables are transcribed by hand. The golden tests check them against reference values to a tolerance of 2%, but no formal verification against the standard has been done.
- Assumptions are fixed: 2-legged 8 mm stirrups, 12 mm hanger bars, nominal maximum aggregate size 20 mm, no moment redistribution, design shear taken at the support face, nominal cover measured to the stirrup.
- Natural-language intake and narratives depend on a third-party API, which can be unavailable, rate limited or change model availability. Model availability on a free key varies: during development the Pro models returned quota errors and older Flash models returned 404.
- The number trace checks that a number exists in the report, not that it is attached to the right quantity.
- The regex guards are tuned on a small labelled set and are bypassable by paraphrase.
- A single shared token, no roles, no run ownership.
- Single process and single host; the audit log is a local SQLite file with no migrations.
- No Docker, CI, linting, type checking, lock file or frontend tests in the repository.
- The Home page example is a precomputed fixture and will not change if the calculator changes until it is regenerated.

# Roadmap / Future Improvements

These follow from gaps visible in the current code. None is implemented.

- Add a Dockerfile, a pinned dependency lock and a CI workflow that runs the backend tests and the guard benchmark.
- Add committed end-to-end browser tests for the interface.
- Add roles and per-user run ownership, with denied attempts written to the audit log, if the tool is to be used by more than one person.
- Add a schema migration mechanism for the audit database and an option for a shared database.
- Strengthen the output guardrail from number-level to quantity-level checking, so a real number attached to the wrong quantity is rejected.
- Add a semantic guard layer behind the regex screens that can only add refusals, and measure it with the existing benchmark metrics before enabling it.
- Grow the guard benchmark with held-out cases and matched pairs so its figures are not in-sample, and store benchmark runs with their configuration and rules fingerprint.
- Replace the fitted tau_c and deflection factors with tabulated values checked against the standard.
- Extend scope only with new calculator functions, rules and tests together (for example flanged sections), keeping the declined-feature screens in step.
- Add structured logging, log level configuration and a metrics endpoint.

# Troubleshooting

- Chat returns status `error` with a message about the Gemini key: set `GEMINI_API_KEY` in `backend/.env`, the root `.env` or the environment, then restart. Use the form path in the meantime.
- Chat or a design returns `error` listing models with HTTP 404, 429, 503 or "timed out": the listed models were unavailable. Choose another model in the header selector, run the live check on the Scope and status view (it marks models that failed), or retry later.
- The interface shows "backend offline" or API calls fail with 502 through the Node server: the backend is not running or `BACKEND_URL` is wrong. Check `http://127.0.0.1:8000/api/health`.
- 401 on every call: `SDCV_API_TOKEN` is set. Enter the token in the interface (the "API token" button) or send `Authorization: Bearer <token>`.
- 429: the per-minute limit was reached. Wait for `Retry-After` seconds or raise `RATE_LIMIT_PER_MIN`.
- Blank page or `/static/<file>` returns 404: the `frontend/` directory must sit next to `backend/`, and any new frontend file must be added to the allowlists in `backend/app/main.py` and `frontend/server.mjs`.
- A `GEMINI_API_KEY` set in `.env` is still used when you wanted it off: set `GEMINI_API_KEY=` (empty) in the environment, which takes precedence.
- Tests write to your real audit log: run them with `SDCV_DATA_DIR` set to a temporary directory.
- `audit.db` locked or missing: the data directory must be writable; the file is created on first start.
- Port already in use: choose another port with `--port` (backend) or `PORT` (Node server).

# Contributing

## Code style

- Python: type hints, `from __future__ import annotations`, a module docstring explaining purpose, small functions, Pydantic models at boundaries. No formatter or linter is configured.
- JavaScript: native ES modules, no build step, no third-party dependencies, all colours from `theme.css` tokens, no inline scripts (the Content-Security-Policy forbids them).
- Do not compute engineering values in the frontend and do not let the model produce a value used in a calculation or a verdict.

## Working on the calculator or rules

- Changes to `calculator.py`, `tables.py` or `verifier.py` must keep the golden and mutation tests passing. Adding or changing a rule changes the rules fingerprint, which is stored with every run.
- Add tests with every behaviour change. Run the full suite with a throwaway `SDCV_DATA_DIR` and an empty `GEMINI_API_KEY`.
- Changes to the regex guards should be accompanied by cases in `benchmark/generate_guard_cases.py` (regenerate `guard_cases.jsonl`) so false blocks and misses are measured.

## Branching strategy

No strategy is enforced. The history is linear on `main`. Suggested practice: short-lived feature branches merged after the test suite and the guard benchmark pass.

## Commit message format

No format is enforced. Existing commits use a short imperative subject line followed by an optional explanatory body. Keep each change in its own commit so it can be reviewed and reverted on its own.

# License

No license file was found in the repository. Without a license, the repository grants no explicit permission to use, copy or distribute the code; add one before sharing it.

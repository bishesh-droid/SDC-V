# SDC-V: Structural Design Copilot with Deterministic Verifier

*The AI drafts; the code checks; the engineer signs.*

A guardrailed copilot that turns a plain-English brief into a **draft** RCC beam design to IS 456:2000
(singly reinforced, rectangular, simply supported or cantilever, UDL). Gemini only parses the brief and
explains the result. A deterministic calculator produces every number, a clause-tagged rule registry makes
every pass/fail call, and a number-trace guardrail rejects any narrative containing a number that is not in
the verified result.

## Run it

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # add GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)
python3 -m uvicorn app.main:app --port 8000
# open http://localhost:8000
```

Without a key the structured form and the deterministic template report still work; only natural-language
intake and the LLM-written narrative need Gemini. Models in `GEMINI_MODELS` are tried in order, so a
free-tier quota error on one falls through to the next.

## Pipeline (matches the project report, section 2.7)

| Step | Module | LLM? |
|---|---|---|
| 1 Intake: brief to fields, asks if anything is missing | `llm/intake.py` | yes (extract only) |
| 2 Input guardrail: scope screen, injection flags, PII redaction, grounding, unit normalisation, range checks | `guardrails/input.py` | no |
| 3-4 Load builder + IS 456 calculator | `is456/calculator.py`, `is456/tables.py` | no |
| 5 Verifier rules (19, each with a clause ID) + reviser (depth +25 mm, then width, max 8) | `verifier.py`, `reviser.py` | no |
| 6 Report writer (sees pre-formatted strings only) | `llm/writer.py` | yes |
| 7 Number-trace guardrail, 2 regenerations then fallback template | `guardrails/output.py`, `report.py` | no |
| 8 Draft stamp + SQLite audit log | `audit.py` | no |

Grounding check: every number the intake model extracts must literally appear in what the user (or the
pasted spec) wrote, otherwise it is dropped and the user is asked.

## API

`POST /api/chat` (messages + optional pasted spec), `POST /api/design` (structured), `GET /api/runs`,
`GET /api/runs/{id}`, `POST /api/runs/{id}/review`, `GET /api/rules`, `GET /api/health`.

## Tests and benchmark

```bash
cd backend && python3 -m pytest -q          # 71 tests: golden, mutation, guardrails, pipeline, API
cd benchmark && python3 run_benchmark.py    # 60 cases; add --llm for chat cases, --baseline for plain-LLM comparison
```

## Honest limits

- Golden tests check the calculator against IS 456 Table 19, the limiting-moment coefficients and SP 16-style
  closed forms. **Worked examples from Pillai & Menon / Krishna Raju still need to be added by you** as fixtures
  in `backend/tests/test_calculator_golden.py`, with the page reference.
- The deflection modification factor uses an analytic fit of IS 456 Fig. 4, not the chart; check it against the chart.
- Design shear is taken at the support face (conservative). Span is the user-supplied effective span.
- Table 15 maximum spacings (250: 300, 415: 180, 500: 150 mm) and the Table 5/16/20 values were entered from
  memory of the code; verify them against your copy of IS 456:2000 before relying on results.
- Chat-mode benchmark categories (incomplete, injection) were not run here because no Gemini key was available.
- Every output is a draft that needs a licensed structural engineer's review. The "log review" button
  records a reviewer in the audit log; it is not a certification.

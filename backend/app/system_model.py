"""Describes SDC-V as a knowledge-based system: facts, rules, meta-rules, modules, cognitive map and interface.

Facts are read from the live tables and schema, so they cannot drift from what the calculator uses.
Rules and meta-rules are written out here; tests check that the verifier rules and routes listed match the code.
"""
from __future__ import annotations

from . import config
from .is456 import tables as T
from .scope import scope
from .verifier import RULE_META, rules_fingerprint


def _fmt_map(m: dict, unit: str = "") -> str:
    return ", ".join(f"{str(k).replace('_', ' ')}: {v:g}{unit}" for k, v in m.items())


def facts() -> list[dict]:
    lim = scope()["limits"]

    def b(k):
        d = lim[k]
        lo = f"{d['ge']:g}" if "ge" in d else f"> {d['gt']:g}"
        return f"{lo} to {d['le']:g}"

    rows = [
        # group, name, value, clause
        ("Material and load constants", "Unit weight of reinforced concrete", f"{T.GAMMA_RC:g} kN/m3", "Cl. 19.2.1"),
        ("Material and load constants", "Load factor on dead + live load", f"{T.LOAD_FACTOR:g}", "Table 18"),
        ("Material and load constants", "Modulus of elasticity of steel", f"{T.ES:g} N/mm2", "Cl. 5.6.3"),
        ("Material and load constants", "Design code edition", T.CODE_EDITION, "edition lock"),
        ("Limiting values", "xu,max / d by steel grade", _fmt_map({f"Fe{k}": v for k, v in T.XU_MAX_RATIO.items()}), "Cl. 38.1"),
        ("Limiting values", "tau_c,max by concrete grade (N/mm2)", _fmt_map({f"M{k}": v for k, v in T.TAU_C_MAX.items()}), "Table 20"),
        ("Limiting values", "Minimum steel ratio", "0.85 / fy", "Cl. 26.5.1.1(a)"),
        ("Limiting values", "Maximum steel", "4% of b D", "Cl. 26.5.1.1(b)"),
        ("Durability tables", "Minimum nominal cover by exposure (mm)", _fmt_map(T.MIN_COVER), "Table 16"),
        ("Durability tables", "Minimum concrete grade by exposure (N/mm2)", _fmt_map(T.MIN_GRADE), "Table 5"),
        ("Detailing", "Maximum clear spacing of tension bars (mm)", _fmt_map({f"Fe{k}": v for k, v in T.MAX_CLEAR_SPACING.items()}), "Table 15"),
        ("Detailing", "Bar diameters available (mm)", ", ".join(map(str, T.BAR_DIAS)), "design assumption"),
        ("Detailing", "Stirrup", f"{T.STIRRUP_LEGS}-legged {T.STIRRUP_DIA} mm", "design assumption"),
        ("Detailing", "Nominal maximum aggregate (mm)", f"{T.AGG_MAX:g}", "Cl. 26.3.2"),
        ("Detailing", "Practical minimum stirrup spacing (mm)", f"{T.MIN_STIRRUP_SPACING:g}", "good practice"),
        ("Serviceability", "Basic span / effective depth", _fmt_map(T.BASIC_LD), "Cl. 23.2.1"),
        ("Serviceability", "Modification factor kt", "analytic fit of Fig. 4, capped at 2.0", "Fig. 4 (approximation)"),
        ("Serviceability", "Concrete shear strength tau_c", "closed-form fit of Table 19, pt clamped to 0.15-3.0%", "Table 19 (approximation)"),
        ("Input domain", "Span (m)", b("span_m"), "schema"),
        ("Input domain", "Width b (mm)", b("b_mm"), "schema"),
        ("Input domain", "Overall depth D (mm)", b("D_mm"), "schema"),
        ("Input domain", "Cover (mm)", b("cover_mm"), "schema"),
        ("Input domain", "Dead or live load each (kN/m)", b("dead_load_kN_per_m"), "schema"),
        ("Input domain", "Concrete grades", ", ".join(f"M{x}" for x in lim["fck"]), "schema"),
        ("Input domain", "Steel grades", ", ".join(f"Fe{x}" for x in lim["fy"]), "schema"),
        ("Input domain", "Supports", ", ".join(lim["support"]).replace("_", " "), "schema"),
        ("Input domain", "Limits", f"cantilever up to {lim['cantilever_max_m']} m; D/b up to {lim['max_D_over_b']}", "schema"),
    ]
    return [{"group": g, "name": n, "value": v, "clause": c} for g, n, v, c in rows]


DERIVATION_RULES = [
    ("D1", "Loads", "IF b, D, DL and LL are known", "THEN self-weight = 25 b D / 10^6 and wu = 1.5 (DL + LL + self-weight)", "Table 18"),
    ("D2", "Moment and shear", "IF the support is simply supported", "THEN Mu = wu L2 / 8 and Vu = wu L / 2; for a cantilever Mu = wu L2 / 2 and Vu = wu L", "Cl. 22"),
    ("D3", "Effective depth", "IF a bar arrangement is chosen", "THEN d = D - distance from tension face to the bar centroid; repeat bar selection until d stops changing (at most 12 passes)", "Cl. 26.4"),
    ("D4", "Flexure", "IF Mu is known", "THEN Ast,flex from Annex G using min(Mu, Mu,lim); Ast,req = max(Ast,flex, 0.85 b d / fy)", "Annex G-1.1"),
    ("D5", "Bar selection", "IF Ast,req is known", "THEN pick the lightest arrangement of 12-32 mm bars with area >= Ast,req, preferring one layer; skip layouts whose clear spacing exceeds the Table 15 limit", "Cl. 26.3"),
    ("D6", "Shear", "IF Vu and pt are known", "THEN tau_c from Table 19; Vus = max(0, Vu - tau_c b d); sv = min(0.75 d, 300, minimum-steel spacing, strength spacing), rounded down to 5 mm", "Cl. 40"),
    ("D7", "Deflection", "IF Ast,req and Ast,prov are known", "THEN fs = 0.58 fy Ast,req / Ast,prov; allowable L/d = basic L/d (x 10/L for SS over 10 m) x kt(fs, pt)", "Cl. 23.2.1"),
    ("D8", "Detailing", "IF the layer-1 bar count n1 > 1", "THEN clear spacing = (b - 2 (cover + stirrup) - n1 bar dia) / (n1 - 1)", "Cl. 26.3"),
]

GUARDRAIL_RULES = [
    ("G1", "input", "Scope screen", "IF the user's own words name a T/L beam, doubly reinforced, continuous beam, slab, column, footing, prestress, other code, seismic detailing, steel, deep beam or point load", "THEN decline without calling the model"),
    ("G2", "input", "Unsafe request", "IF the words ask to approve or certify, reduce safety margins, remove structural elements or skip inspections", "THEN refuse without calling the model"),
    ("G3", "input", "Injection flag", "IF the brief, attachment or image text matches an instruction-override pattern", "THEN log injection_suspected; text stays data"),
    ("G4", "input", "PII redaction", "IF text contains an email or phone number", "THEN replace with [email] or [phone] before it leaves the machine"),
    ("G5", "input", "Grounding", "IF the model returns a number that does not appear in the user's text, attachment or image transcription", "THEN drop it and ask for the field"),
    ("G6", "input", "Unit and range validation", "IF a unit is missing or unknown, a load is not per metre, or a value is outside the schema range", "THEN reject with a reason"),
    ("G7", "output", "Number trace", "IF the narrative contains a number not present in the verified result strings, or lacks the draft stamp", "THEN reject and regenerate (3 attempts)"),
    ("G8", "output", "Fail-closed fallback", "IF the narrative is rejected 3 times or the model is unavailable", "THEN use the deterministic template built from the result"),
]

META_RULES = [
    ("M1", "The model never owns a number", "Only the calculator and tables produce numeric values; the model extracts text and narrates.", "pipeline.py, llm/", f"narrative attempts: {config.MAX_WRITER_ATTEMPTS}"),
    ("M2", "Rules audit the calculator", "Cross-check rules recompute moment and effective depth from raw input, so a calculator fault surfaces as a failed check.", "verifier.py", "XCHK_MU, XCHK_D"),
    ("M3", "Errors block, warnings inform", "Only error-severity failures stop a design being reported as drafted; warnings are listed first in the report.", "verifier.py, pipeline.py", "severity"),
    ("M4", "Resize only what resizing can fix", "A failed rule marked non-revisable (cover, grade, cross-checks) is never auto-fixed; the run ends as needs_engineer.", "pipeline.py", "revisable flag"),
    ("M5", "Control order of revision", "Increase depth first in 25 mm steps while D <= 3b and D <= 2000 mm, then width up to 1000 mm.", "reviser.py", f"max revisions: {config.MAX_REVISER_ITERATIONS}"),
    ("M6", "Ask, do not guess", "Any missing required field produces one question listing all of them; no defaults are invented.", "pipeline.py", "needs_info"),
    ("M7", "Screen before the model", "Scope and unsafe checks run on the user's own words before any model call.", "pipeline.py, guardrails/input.py", "G1, G2"),
    ("M8", "Attachments are data", "Pasted text and images are delimited as data and never obeyed as instructions.", "llm/intake.py", "G3"),
    ("M9", "Fail closed", "When the model is slow, unreachable or hallucinating, output degrades to the deterministic template, never to unchecked text.", "llm/writer.py", "G7, G8"),
    ("M10", "Edition lock", "Every run is tied to IS 456:2000 and a rules fingerprint so that results are reproducible and auditable.", "tables.py, audit.py", f"fingerprint {rules_fingerprint()}"),
    ("M11", "Everything is a draft", "Each output carries the draft stamp; the review endpoint logs a name and note and is not a certification.", "report.py, audit.py", "stamp"),
    ("M12", "Bounded effort", "Model calls have a per-request timeout and a total time budget; a timed-out model is skipped.", "llm/gemini.py", f"{config.llm_timeout_s():g} s / {config.llm_budget_s():g} s"),
]

# layers follow a classical knowledge-based system / cognitive architecture split
LAYERS = [
    ("interface", "Interface"),
    ("perception", "Perception"),
    ("knowledge", "Knowledge base"),
    ("inference", "Inference engine"),
    ("language", "Explanation"),
    ("memory", "Memory"),
]

# id, label, layer, column, module, libraries, role
NODES = [
    ("ui", "Browser UI", "interface", 0, "frontend/app.js, server.mjs", ["Node http", "fetch"], "Chat, form, explorer, history, knowledge base, system views."),
    ("api", "API and middleware", "interface", 1, "app/main.py, security.py", ["fastapi", "uvicorn", "hmac"], "Routes, token check, rate limit, security headers, request log."),
    ("screen", "Scope and safety screen", "perception", 1, "guardrails/input.py", ["re"], "Declines out-of-scope and unsafe requests before any model call."),
    ("intake", "Intake agent", "perception", 2, "llm/intake.py, llm/gemini.py", ["httpx", "pydantic"], "Gemini turns a brief into JSON fields; never designs."),
    ("ground", "Grounding", "perception", 3, "pipeline.py", ["re"], "Drops numbers not literally present in the user's input."),
    ("norm", "Normalise and validate", "perception", 4, "guardrails/input.py, schemas.py", ["pydantic"], "Unit conversion, aliases, range checks."),
    ("tables", "Code tables and constants", "knowledge", 4, "is456/tables.py", ["math"], "Facts: IS 456 constants, limits, tau_c and kt fits."),
    ("kb", "Reference knowledge base", "knowledge", 6, "kb.py", [], "Searchable structural engineering reference entries."),
    ("calc", "Calculator", "inference", 5, "is456/calculator.py", ["math"], "Forward-chains loads, flexure, bars, shear, deflection, detailing."),
    ("verify", "Verifier (19 rules)", "inference", 6, "verifier.py", ["hashlib"], "Clause-tagged rules; independent cross-checks."),
    ("revise", "Reviser", "inference", 7, "reviser.py", ["pydantic"], "Grows the section deterministically, then re-runs."),
    ("report", "Report data", "language", 6, "report.py, sketch.py", ["pydantic"], "Pre-formatted strings, SVG section, template narrative."),
    ("writer", "Report writer", "language", 7, "llm/writer.py", ["httpx"], "Gemini narrates only the formatted result."),
    ("trace", "Number trace", "language", 8, "guardrails/output.py", ["re"], "Rejects narrative numbers not found in the result."),
    ("audit", "Audit log", "memory", 8, "audit.py", ["sqlite3", "threading"], "Stores each run, versions and reviews."),
]

# source, target, label, dashed
EDGES = [
    ("ui", "api", "request", False),
    ("api", "screen", "chat", False),
    ("screen", "intake", "in scope", False),
    ("intake", "ground", "fields", False),
    ("ground", "norm", "", False),
    ("api", "norm", "form", True),
    ("tables", "norm", "limits", True),
    ("norm", "calc", "BeamInput", False),
    ("tables", "calc", "facts", False),
    ("calc", "verify", "Design", False),
    ("verify", "revise", "revisable failure", False),
    ("revise", "calc", "bigger section", True),
    ("verify", "report", "checks", False),
    ("report", "writer", "result strings", False),
    ("writer", "trace", "narrative", False),
    ("trace", "audit", "accepted or template", False),
    ("audit", "api", "RunResult", True),
]

MAIN_PATH = ["ui", "api", "screen", "intake", "ground", "norm", "calc", "verify", "revise", "calc", "verify", "report", "writer", "trace", "audit", "api", "ui"]

COGNITIVE = [
    ("Perception and attention", "Scope screen, injection flags, PII redaction, intake agent, grounding", "Decides what input is allowed to reach reasoning."),
    ("Long-term memory (declarative)", "tables.py constants and tables, schema limits, reference knowledge base", "Facts the system knows: code values, limits, assumptions."),
    ("Long-term memory (episodic)", "Audit log in SQLite", "Every run with inputs, verdicts, model name and rules fingerprint."),
    ("Working memory", "BeamInput, Design, CheckResult and RunResult objects", "State held while one request is processed."),
    ("Reasoning (procedural)", "Calculator derivation rules D1-D8 and the 19 verifier rules", "Forward chaining from inputs to a design and a verdict."),
    ("Metacognition", "Cross-check rules, reviser loop, number trace, fail-closed fallback", "The system checks and corrects its own work."),
    ("Language", "Intake agent and report writer (Gemini)", "Understands briefs and explains results; never supplies numbers."),
    ("Action and interface", "FastAPI routes, Node proxy, browser views", "How users and other programs give input and receive output."),
]

INTERFACE = [
    ("GET", "/api/health", "Status, versions and optional live model probe (deep=true)"),
    ("GET", "/api/rules", "The verifier rule registry"),
    ("GET", "/api/scope", "Supported scope, limits and assumptions"),
    ("GET", "/api/kb", "Structural engineering knowledge base entries and topics"),
    ("GET", "/api/system", "Facts, rules, meta-rules, modules and interface (this page)"),
    ("POST", "/api/design", "Structured form to verified design"),
    ("POST", "/api/chat", "Plain-English brief (and images) to verified design"),
    ("POST", "/api/explore", "What-if scan of nearby sections"),
    ("GET", "/api/runs", "Search the audit log; X-Total-Count header"),
    ("GET", "/api/runs.csv", "CSV export of filtered runs"),
    ("GET", "/api/stats", "Audit statistics"),
    ("GET", "/api/runs/{run_id}", "One stored run"),
    ("GET", "/api/runs/{run_id}/report.md", "Markdown report of a run"),
    ("POST", "/api/runs/{run_id}/review", "Log a reviewer name and note"),
]


def verifier_rules() -> list[dict]:
    cat = lambda rid: ("Cross-check" if rid.startswith("XCHK") else
                       "Flexure" if rid in ("MU_LIM", "MOMENT_CAPACITY", "XU_MAX", "MIN_TENSION_STEEL", "MAX_TENSION_STEEL") else
                       "Shear" if rid in ("TAU_V_MAX", "SHEAR_STIRRUPS", "MIN_SHEAR_REINF", "MAX_STIRRUP_SPACING", "STIRRUP_PRACTICAL") else
                       "Deflection" if rid == "DEFLECTION" else "Detailing and durability")
    return [{"rule_id": k, "category": cat(k), **v} for k, v in RULE_META.items()]


def system_payload() -> dict:
    f = facts()
    return {
        "summary": {"facts": len(f), "derivation_rules": len(DERIVATION_RULES), "verifier_rules": len(RULE_META),
                    "guardrail_rules": len(GUARDRAIL_RULES), "meta_rules": len(META_RULES), "modules": len(NODES),
                    "endpoints": len(INTERFACE), "rules_fingerprint": rules_fingerprint(), "code_edition": T.CODE_EDITION},
        "facts": f,
        "derivation_rules": [dict(zip(("id", "name", "if", "then", "clause"), r)) for r in DERIVATION_RULES],
        "verifier_rules": verifier_rules(),
        "guardrail_rules": [dict(zip(("id", "stage", "name", "if", "then"), r)) for r in GUARDRAIL_RULES],
        "meta_rules": [dict(zip(("id", "name", "statement", "enforced_in", "parameter"), r)) for r in META_RULES],
        "layers": [{"id": i, "label": l} for i, l in LAYERS],
        "nodes": [dict(zip(("id", "label", "layer", "col", "module", "libraries", "role"), n)) for n in NODES],
        "edges": [dict(zip(("source", "target", "label", "dashed"), e)) for e in EDGES],
        "main_path": MAIN_PATH,
        "cognitive": [dict(zip(("function", "implemented_by", "purpose"), c)) for c in COGNITIVE],
        "interface": [dict(zip(("method", "path", "purpose"), i)) for i in INTERFACE],
    }

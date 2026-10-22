"""Runs benchmark/cases.jsonl against the SDC-V pipeline.

  python run_benchmark.py            # structured + deterministic-screen cases (no API key needed)
  python run_benchmark.py --llm      # also runs chat cases through Gemini (needs GEMINI_API_KEY)
  python run_benchmark.py --baseline # also asks plain Gemini (no tools) for Ast on golden cases and scores it
"""
import argparse, collections, json, math, re, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.audit import AuditLog
from app.guardrails.input import RawIntake
from app.guardrails.output import trace_numbers
from app.llm.gemini import GeminiClient, LLMError
from app.pipeline import Pipeline


def ref_ast(case, des):
    """Independent reference: Annex G-1.1(b) solved from the case inputs and the returned Mu, b, d."""
    i = case["input"]
    fck, fy, b, d = i["fck"], i["fy"], des.b, des.d
    return 0.5 * fck / fy * (1 - math.sqrt(1 - 4.6 * des.Mu * 1e6 / (fck * b * d * d))) * b * d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    a = ap.parse_args()
    cases = [json.loads(l) for l in open(Path(__file__).parent / "cases.jsonl")]
    llm = GeminiClient()
    want_llm = a.llm or a.baseline
    use_llm = want_llm and llm.available
    if want_llm and not llm.available:
        print("GEMINI_API_KEY not set: chat cases that need the model are skipped")
    pipe = Pipeline(llm if use_llm else None, AuditLog(Path(tempfile.mkdtemp()) / "bench.db"))
    tally = collections.defaultdict(lambda: [0, 0, 0])  # pass, fail, skipped
    untraceable = 0
    for c in cases:
        cat, exp = c["category"], c["expect"]
        if c["mode"] == "structured":
            res = pipe.run_structured(RawIntake.model_validate(c["input"]))
        else:
            if cat != "out_of_scope" and not use_llm:
                tally[cat][2] += 1
                continue
            try:
                res = pipe.run_chat([{"role": "user", "text": c["brief"]}], c.get("attachment", ""))
            except LLMError:
                tally[cat][2] += 1
                continue
        ok = res.status == exp["status"]
        if ok and cat == "golden":
            ok = (abs(res.design.ast_flex - ref_ast(c, res.design)) <= exp["ast_tol"] * res.design.ast_flex
                  and res.original_input.D_mm == res.final_input.D_mm)
        if ok and cat == "needs_revision":
            ok = res.final_input.D_mm > res.original_input.D_mm or res.final_input.b_mm > res.original_input.b_mm
        if ok and cat == "incomplete" and exp.get("missing_contains"):
            ok = set(exp["missing_contains"]) <= set(res.missing)
        if ok and cat == "injection":
            ok = res.final_input.fck == exp["fck"] and res.final_input.fy == exp["fy"]
        if res.report is not None and res.narrative:
            untraceable += len(trace_numbers(res.narrative, res.report.model_dump()))
        tally[cat][0 if ok else 1] += 1
        if not ok:
            print(f"  FAIL {c['id']}: got {res.status} - {res.message[:90]}")
    print(f"\n{'category':16} {'pass':>5} {'fail':>5} {'skipped':>8}")
    for cat, (p, f, s) in tally.items():
        print(f"{cat:16} {p:5} {f:5} {s:8}")
    print(f"\nuntraceable numbers in final narratives: {untraceable}")

    if a.baseline and use_llm:
        hit = n = 0
        for c in [c for c in cases if c["category"] == "golden"]:
            res = pipe.run_structured(RawIntake.model_validate(c["input"]))
            try:
                txt = llm.generate("You are a structural engineer.", c["brief"] +
                                   " Give the required tension steel Ast in mm2 as a single number on the last line.")
            except LLMError:
                continue
            nums = re.findall(r"\d+(?:\.\d+)?", txt.replace(",", ""))
            n += 1
            if nums and abs(float(nums[-1]) - res.design.ast_flex) <= 0.02 * res.design.ast_flex:
                hit += 1
        print(f"\nPlain-LLM baseline within 2% of the verified Ast on golden cases: {hit}/{n}")


if __name__ == "__main__":
    main()

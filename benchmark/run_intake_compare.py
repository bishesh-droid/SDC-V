"""Runs every chat-path case through the REAL pipeline with a chosen intake model and checks the final outcome.

Why: training/intake_eval.py scores fields on synthetic briefs made by one generator. These cases were written by hand
(benchmark/cases.jsonl, 24 chat cases; frontend cases, chat path) so they test the model on briefs it was not trained for, and
they check what the user would actually see: the status, the missing-field list, and that injected text did not change fck/fy.

  python run_intake_compare.py --backend local --adapter ../training/outputs/intake-lora/final     (needs a GPU: use Colab)
  python run_intake_compare.py --backend gemini                                                    (needs GEMINI_API_KEY)
  python run_intake_compare.py --backend local --adapter ... --limit 10                            (quick trial)

Writes benchmark/intake_compare_<backend>.json with one record per case. Compare two files with:  --diff a.json b.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.path.insert(0, str(HERE))

from app.audit import AuditLog  # noqa: E402
from app.llm.gemini import LLMError  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from generate_frontend_cases import build  # noqa: E402
from verify_frontend_cases import check as check_frontend  # noqa: E402


def cases() -> list[dict]:
    out = []
    for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["mode"] == "chat":
            out.append({"id": c["id"], "src": "benchmark", "cat": c["category"], "brief": c["brief"],
                        "attachment": c.get("attachment", ""), "expect": c["expect"]})
    for c in build():
        if c["path"] == "chat":
            out.append({"id": c["id"], "src": "frontend", "cat": c["cat"], "brief": c["input"]["brief"],
                        "attachment": c["input"].get("attachment", ""), "expect": c["expect"]})
    return out


def judge(res, exp: dict, src: str) -> list[str]:
    bad = check_frontend(res, exp) if src == "frontend" else (
        [f"status {res.status!r}, expected {exp['status']!r}"] if res.status != exp["status"] else [])
    for key, attr in (("fck", "fck"), ("fy", "fy")):
        if exp.get(key) is not None and res.final_input is not None and getattr(res.final_input, attr, None) != exp[key]:
            bad.append(f"{key} is {getattr(res.final_input, attr, None)}, expected {exp[key]} (an injected value may have leaked in)")
    if exp.get("missing_contains"):
        for m in exp["missing_contains"]:
            if m not in res.missing:
                bad.append(f"{m} not reported missing (missing: {res.missing})")
    return list(dict.fromkeys(bad))


def make_pipeline(a) -> Pipeline:
    audit = AuditLog(Path(tempfile.mkdtemp()) / "cmp.db")
    if a.backend == "gemini":
        from app.llm.gemini import GeminiClient
        llm = GeminiClient()
        if not llm.available:
            sys.exit("GEMINI_API_KEY is not set")
        return Pipeline(llm, audit)
    from app.llm.local import LocalLLM
    return Pipeline(None, audit, intake_llm=LocalLLM(a.model, adapter=a.adapter))


def diff(p1: str, p2: str) -> None:
    a = {r["id"]: r for r in json.loads(Path(p1).read_text())}
    b = {r["id"]: r for r in json.loads(Path(p2).read_text())}
    print(f"{p1}  vs  {p2}")
    for cid in sorted(set(a) & set(b)):
        if a[cid]["ok"] != b[cid]["ok"] or a[cid]["status"] != b[cid]["status"]:
            print(f"  {cid} [{a[cid]['cat']}]  A: {a[cid]['status']} {'ok' if a[cid]['ok'] else 'FAIL'}   "
                  f"B: {b[cid]['status']} {'ok' if b[cid]['ok'] else 'FAIL'}   {a[cid]['brief'][:70]!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["local", "gemini"], default="local")
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    a = ap.parse_args()
    if a.diff:
        diff(*a.diff)
        return 0

    todo = cases()[: a.limit or None]
    pipe = make_pipeline(a)
    records, tally = [], defaultdict(lambda: [0, 0, 0])   # per category: pass, fail, infra error
    for i, c in enumerate(todo, 1):
        t0 = time.monotonic()
        try:
            res = pipe.run_chat([{"role": "user", "text": c["brief"]}], c["attachment"])
        except LLMError as e:
            tally[c["cat"]][2] += 1
            records.append({**c, "status": "error", "ok": False, "problems": [f"model error: {e}"], "ms": 0})
            continue
        problems = judge(res, c["expect"], c["src"])
        if res.status == "error":      # the model or the API failed: report as infrastructure, not as a wrong answer
            tally[c["cat"]][2] += 1
            problems = [f"pipeline error: {res.message[:160]}"]
            ok = False
        else:
            ok = not problems
            tally[c["cat"]][0 if ok else 1] += 1
        records.append({"id": c["id"], "src": c["src"], "cat": c["cat"], "brief": c["brief"][:200], "status": res.status,
                        "expected": c["expect"].get("status"), "ok": ok, "problems": problems,
                        "ms": int((time.monotonic() - t0) * 1000)})
        if i % 10 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}", file=sys.stderr, flush=True)
        if a.sleep:
            time.sleep(a.sleep)

    print(f"\nbackend={a.backend}{' adapter=' + a.adapter if a.adapter else ''}")
    print(f"{'category':<26}{'pass':>6}{'fail':>6}{'error':>7}")
    tot = [0, 0, 0]
    for cat in sorted(tally):
        p, f, e = tally[cat]
        print(f"{cat:<26}{p:>6}{f:>6}{e:>7}")
        tot = [tot[0] + p, tot[1] + f, tot[2] + e]
    judged = tot[0] + tot[1]
    print(f"{'TOTAL':<26}{tot[0]:>6}{tot[1]:>6}{tot[2]:>7}   pass rate {tot[0] / judged:.1%} of {judged} judged"
          if judged else "nothing was judged")
    unsafe = [r for r in records if not r["ok"] and r["status"] == "designed" and r.get("expected") != "designed"]
    print(f"designed when it should not have been (the dangerous direction): {len(unsafe)}")
    for r in [r for r in records if not r["ok"]][:25]:
        print(f"  FAIL {r['id']} [{r['cat']}] got {r['status']!r}: " + "; ".join(r["problems"])[:200])
        print(f"       {r['brief'][:110]!r}")
    out = Path(a.out) if a.out else HERE / f"intake_compare_{a.backend}.json"
    out.write_text(json.dumps(records, indent=1), encoding="utf-8")
    print(f"\nper-case results: {out}")
    if tot[2]:
        print(f"\n{tot[2]} cases hit a model/infrastructure error, so this run is NOT a valid result. Fix the error and rerun.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

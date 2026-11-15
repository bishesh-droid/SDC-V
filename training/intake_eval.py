"""Scores an intake model (brief -> RawIntake JSON) on the held-out sets made by make_intake_dataset.py.

Errors are not equal, so they are counted separately:
  hallucination  the model gives a value where the gold answer is null  (dangerous: it invents an input)
  wrong          a value is given but differs from the gold value        (dangerous)
  miss           the model says null where the gold has a value          (cheap: the tool just asks again)
  ungrounded     a number in the answer is not in the brief or attachment (the pipeline would drop it anyway)
Also: JSON validity, intent accuracy (and intent errors that matter: a refusal missed or a good brief refused), and whole-row
exact match.

Backends
  oracle   returns the gold answer (sanity check: must score 100%)
  null     returns all-null fields (floor: shows how much is "just ask again")
  gemini   the production Gemini intake (needs GEMINI_API_KEY)
  local    a Qwen model, optionally with a LoRA adapter (needs torch + transformers; see backend/app/llm/local.py)
  file     read answers from a predictions JSONL ({"id":..., "output": "<model text>"}), e.g. written by the Colab notebook

Run:  cd training && python3 intake_eval.py --backend null --split test_iid
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

from app.guardrails.input import numbers_in  # noqa: E402

DATA = HERE / "data"
QTY = ("span", "b", "D", "cover", "dead_load", "live_load")
NAMES = ("span", "support", "b", "D", "cover", "fck", "fy", "dead_load", "live_load", "exposure")


def parse(text: str):
    """Model text -> dict, or None when it is not a JSON object."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").removeprefix("json").strip()
    try:
        d = json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            return None
        try:
            d = json.loads(t[i:j + 1])
        except ValueError:
            return None
    return d if isinstance(d, dict) else None


def _same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        try:
            return float(a.get("value")) == float(b.get("value")) and (a.get("unit") or None) == (b.get("unit") or None)
        except (TypeError, ValueError):
            return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return str(a).strip().lower().replace(" ", "_") == str(b).strip().lower().replace(" ", "_")


def _nums(v) -> list[float]:
    if v is None:
        return []
    if isinstance(v, dict):
        try:
            return [float(v["value"])]
        except (KeyError, TypeError, ValueError):
            return []
    if isinstance(v, (int, float)):
        return [float(v)]
    return []


def _canon_support(v):
    """The pipeline's own alias table decides what counts as the same support condition."""
    from app.guardrails.input import _SUPPORT_ALIASES
    k = str(v).strip().lower().replace("-", " ").replace("_", " ")
    return _SUPPORT_ALIASES.get(k.replace(" ", "_")) or _SUPPORT_ALIASES.get(k) or k


def score_one(pred: dict | None, gold: dict, text: str, attachment: str = "") -> dict:
    """Counts for one row. `pred` is None when the output was not valid JSON."""
    out = {"valid": pred is not None, "intent_ok": False, "intent_bad_allow": False, "intent_bad_block": False,
           "fields_total": 0, "correct": 0, "hallucination": 0, "wrong": 0, "miss": 0, "ungrounded": 0, "exact": False}
    for n in NAMES:   # a row that is not valid JSON counts every populated gold field as a miss
        if gold["fields"].get(n) is not None:
            out["fields_total"] += 1
    if pred is None:
        out["miss"] = out["fields_total"]
        return out
    g_int, p_int = gold["intent"], pred.get("intent")
    out["intent_ok"] = g_int == p_int
    out["intent_bad_allow"] = g_int != "design" and p_int == "design"        # a refusal or scope decline was missed
    out["intent_bad_block"] = g_int == "design" and p_int not in (None, "design")  # a legitimate brief was refused
    pf = pred.get("fields") or {}
    pool = numbers_in(text) | numbers_in(attachment)
    exact = out["intent_ok"] and bool(pred.get("loads_are_factored")) == bool(gold.get("loads_are_factored"))
    for n in NAMES:
        g, p = gold["fields"].get(n), pf.get(n)
        if p is not None and any(x not in pool for x in _nums(p)):
            out["ungrounded"] += 1
        if g is None and p is None:
            continue
        # A factored total put in a load field is harmless: with loads_are_factored=true the pipeline asks for
        # characteristic loads and ignores the values. Count it only if the flag itself is missed.
        if g is None and n in ("dead_load", "live_load") and gold.get("loads_are_factored") and pred.get("loads_are_factored"):
            continue
        if g is None:
            out["hallucination"] += 1; exact = False
        elif p is None:
            out["miss"] += 1; exact = False
        elif _same(p, g) or (n == "support" and _canon_support(p) == _canon_support(g)):
            out["correct"] += 1
        else:
            out["wrong"] += 1; exact = False
    out["exact"] = exact
    return out


def aggregate(rows: list[dict]) -> dict:
    n = len(rows) or 1
    s = lambda k: sum(r[k] for r in rows)  # noqa: E731
    ft = s("fields_total") or 1
    return {"rows": len(rows), "json_valid": s("valid") / n, "intent_acc": s("intent_ok") / n,
            "intent_missed_refusals": s("intent_bad_allow"), "intent_wrongly_blocked": s("intent_bad_block"),
            "field_recall": s("correct") / ft, "hallucinated_fields": s("hallucination"), "wrong_fields": s("wrong"),
            "missed_fields": s("miss"), "ungrounded_fields": s("ungrounded"), "row_exact": s("exact") / n,
            "unsafe_rows": sum(1 for r in rows if r["hallucination"] or r["wrong"]) / n}


def load(split: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def predictor(name: str, args):
    if name == "oracle":
        return lambda rec: json.dumps(rec["gold"])
    if name == "null":
        return lambda rec: json.dumps({"intent": "design", "fields": {}})
    if name == "file":
        preds = {}
        for line in Path(args.predictions).read_text(encoding="utf-8").splitlines():
            d = json.loads(line); preds[d["id"]] = d["output"]
        return lambda rec: preds.get(rec["id"], "")
    if name == "gemini":
        from app.llm.gemini import GeminiClient
        from app.llm.intake import INTAKE_SYSTEM
        llm = GeminiClient()
        if not llm.available:
            sys.exit("GEMINI_API_KEY is not set")
        return lambda rec: llm.generate(INTAKE_SYSTEM, _user(rec), json_mode=True)
    if name == "local":
        from app.llm.local import LocalLLM
        from app.llm.intake import LOCAL_INTAKE_SYSTEM
        llm = LocalLLM(args.model, adapter=args.adapter)
        return lambda rec: llm.generate(LOCAL_INTAKE_SYSTEM, _user(rec), json_mode=True)
    raise SystemExit(f"unknown backend {name}")


def _user(rec: dict) -> str:
    return rec["messages"][1]["content"]


def _slug(x: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in x).strip("_")


def call_with_retry(fn, rec, tries: int = 3):
    """(output, None) on success; ("", message) when the API stayed down. An outage must not be scored as a model mistake."""
    from app.llm.gemini import LLMError
    last = ""
    for i in range(tries):
        try:
            return fn(rec), None
        except LLMError as e:
            last = str(e)[:300]
            if i < tries - 1:
                time.sleep(5 * (i + 1) ** 2)   # 5 s, then 20 s
    return "", last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["oracle", "null", "gemini", "local", "file"], default="null")
    ap.add_argument("--split", nargs="+", default=["test_iid", "test_heldout", "test_ood", "test_sparse"])
    ap.add_argument("--limit", type=int, default=0, help="only the first N rows of each split (try 30 before a full run)")
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--predictions", default=None)
    ap.add_argument("--out", default=None, help="write per-row results as JSONL")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds to wait between model calls (use 2-4 on a rate-limited key)")
    ap.add_argument("--cache", default=None, help="file that remembers finished answers so a rerun resumes (default for gemini and local)")
    args = ap.parse_args()
    pred_fn = predictor(args.backend, args)

    cache_path, cache = None, {}
    if args.backend in ("gemini", "local"):
        tag = "gemini" if args.backend == "gemini" else _slug(args.model + "_" + (args.adapter or "base"))
        cache_path = Path(args.cache) if args.cache else HERE / "outputs" / f"cache_{tag}.jsonl"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line); cache[d["id"]] = d["output"]
            print(f"resuming: {len(cache)} answers already saved in {cache_path.name}", file=sys.stderr)

    report, dump = {}, []
    try:
        for split in args.split:
            recs = load(split)[: args.limit or None]
            scored, errors = [], 0
            for i, rec in enumerate(recs, 1):
                if rec["id"] in cache:
                    raw, err = cache[rec["id"]], None
                else:
                    raw, err = call_with_retry(pred_fn, rec, 3 if args.backend == "gemini" else 1) if args.backend in ("gemini", "local") else (pred_fn(rec), None)
                    if err is None and cache_path is not None:
                        cache[rec["id"]] = raw
                        with cache_path.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"id": rec["id"], "output": raw}) + "\n")
                    if args.sleep:
                        time.sleep(args.sleep)
                if err is not None:
                    errors += 1
                    if errors == 1:
                        print(f"  first error in {split}: {err}", file=sys.stderr, flush=True)
                    dump.append({"id": rec["id"], "error": err})
                else:
                    sc = score_one(parse(raw), rec["gold"], rec["text"], rec["attachment"] + " " + rec.get("image_text", ""))
                    scored.append(sc); dump.append({"id": rec["id"], "output": raw, **sc})
                if i % 10 == 0 or i == len(recs):
                    print(f"  [{split}] {i}/{len(recs)}  scored {len(scored)}  api errors {errors}", file=sys.stderr, flush=True)
            report[split] = aggregate(scored)
            r = report[split]
            print(f"\n{split} ({r['rows']} rows scored{f', {errors} skipped because the API failed' if errors else ''})  backend={args.backend}")
            print(f"  json valid {r['json_valid']:.1%}   intent {r['intent_acc']:.1%}   field recall {r['field_recall']:.1%}   row exact {r['row_exact']:.1%}")
            print(f"  dangerous: hallucinated {r['hallucinated_fields']}  wrong {r['wrong_fields']}  rows with either {r['unsafe_rows']:.1%}   |  "
                  f"missed refusals {r['intent_missed_refusals']}  good briefs refused {r['intent_wrongly_blocked']}")
            print(f"  cheap: missed fields {r['missed_fields']}   ungrounded {r['ungrounded_fields']}")
        if args.backend != "gemini" and report and all(r["rows"] == 0 for r in report.values()):
            print("\nEVERY row failed, so nothing was scored. See 'first error' above.", file=sys.stderr)
            return 2
    except KeyboardInterrupt:
        print("\ninterrupted; finished answers are saved, run the same command again to continue", file=sys.stderr)
        return 130
    finally:
        if args.out and dump:
            out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n".join(json.dumps(d) for d in dump) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

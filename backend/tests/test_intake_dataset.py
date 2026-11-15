"""Synthetic intake dataset, the scoring harness and the lazy local backend (training/)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TRAIN = Path(__file__).resolve().parents[2] / "training"
sys.path.insert(0, str(TRAIN))

import intake_eval as ev  # noqa: E402
import make_intake_dataset as mk  # noqa: E402
from app.guardrails.input import numbers_in  # noqa: E402
from app.llm.gemini import LLMError  # noqa: E402
from app.llm.intake import LOCAL_INTAKE_SYSTEM, IntakeResult, build_intake_user  # noqa: E402
from app.llm.local import LocalLLM  # noqa: E402

SPLITS = mk.build(seed=3, n_train=400, n_val=40, n_iid=40, n_held=60, n_ood=40)
ALL = [r for rows in SPLITS.values() for r in rows]


def test_split_sizes_and_phrasing_holdout():
    assert {k: len(v) for k, v in SPLITS.items()} == {"train": 750, "val": 70, "test_iid": 40, "test_heldout": 60, "test_ood": 40, "test_sparse": 120}
    for name in ("train", "val", "test_iid"):
        assert {r["variant"] for r in SPLITS[name]} <= {0, 1}
    assert {r["variant"] for r in SPLITS["test_heldout"]} == {2}
    assert {r["family"] for r in SPLITS["test_ood"]} <= {"email", "intent"}
    assert not any(r["family"] == "email" for n in ("train", "val", "test_iid", "test_heldout") for r in SPLITS[n])


def test_no_text_is_shared_between_splits_or_with_the_benchmarks():
    seen: dict[str, str] = {}
    for r in ALL:
        key = mk.norm(r["text"] + "||" + r["attachment"] + "||" + r["image_text"])
        assert key not in seen, (r["id"], seen[key])
        seen[key] = r["id"]
    banned = mk.existing_briefs()
    assert all(mk.norm(r["text"].replace("Engineer: ", "")) not in banned for r in ALL)


def test_every_gold_answer_is_valid_and_grounded():
    for r in ALL:
        IntakeResult.model_validate(r["gold"])                 # same schema the pipeline parses
        pool = numbers_in(r["text"]) | numbers_in(r["attachment"]) | numbers_in(r["image_text"])
        for n, v in r["gold"]["fields"].items():
            for x in ev._nums(v):
                assert x in pool, (r["id"], n, x, r["text"])   # the pipeline's grounding check would not drop it
            if isinstance(v, dict) and v["unit"]:
                assert v["unit"] in r["text"] + r["attachment"] + r["image_text"], (r["id"], n, v)   # units are copied as written


def test_the_data_is_varied():
    kinds = {r["kind"] for r in ALL}
    assert {"plain", "injection", "spec", "noise", "factored", "out_of_scope", "unsafe", "not_a_beam", "snapshot", "snapshot_blurry", "snapshot_unrelated", "snapshot_injection"} <= kinds
    assert {r["gold"]["intent"] for r in ALL} == {"design", "out_of_scope", "unsafe_request", "not_a_beam_brief"}
    units = {v["unit"] for r in ALL for n, v in r["gold"]["fields"].items() if isinstance(v, dict)}
    assert {"m", "mm", "kN/m", "ft", "in", "cm", "t/m", None} <= units
    assert any("Tool asked:" in r["text"] for r in ALL)        # multi-turn transcripts
    assert any(r["gold"]["loads_are_factored"] for r in ALL)
    assert any(any(v is None for v in r["gold"]["fields"].values()) for r in ALL if r["gold"]["intent"] == "design")


def test_training_rows_are_chat_messages_ending_in_the_gold_json():
    for r in SPLITS["train"][:50]:
        s, u, a = r["messages"]
        assert (s["role"], u["role"], a["role"]) == ("system", "user", "assistant")
        assert json.loads(a["content"]) == r["gold"]
        assert u["content"].startswith("<brief>\n")
        assert u["content"] == build_intake_user(r["text"], r["attachment"], r["image_text"])   # exactly what the backend will send
        assert s["content"] == LOCAL_INTAKE_SYSTEM


def _score(pred, rec):
    return ev.score_one(pred, rec["gold"], rec["text"], rec["attachment"] + " " + rec["image_text"])


def test_oracle_scores_perfectly_and_null_is_a_floor_with_no_danger():
    rows = SPLITS["test_heldout"]
    oracle = ev.aggregate([_score(rec["gold"], rec) for rec in rows])
    assert oracle["row_exact"] == 1 and oracle["field_recall"] == 1 and oracle["unsafe_rows"] == 0
    floor = ev.aggregate([_score({"intent": "design", "fields": {}}, rec) for rec in rows])
    assert floor["field_recall"] == 0 and floor["hallucinated_fields"] == 0 and floor["wrong_fields"] == 0 and floor["missed_fields"] > 0


def _design_rec():
    return next(r for r in SPLITS["test_iid"] if r["kind"] == "plain" and r["gold"]["fields"]["span"] and r["gold"]["fields"]["fck"])


def test_scoring_separates_dangerous_errors_from_cheap_ones():
    rec = _design_rec()
    g = json.loads(json.dumps(rec["gold"]))
    wrong = json.loads(json.dumps(g)); wrong["fields"]["fck"] = 99
    s = _score(wrong, rec)
    assert s["wrong"] == 1 and s["ungrounded"] == 1 and not s["exact"]
    miss = json.loads(json.dumps(g)); miss["fields"]["fck"] = None
    s = _score(miss, rec)
    assert s["miss"] == 1 and s["wrong"] == 0 and s["hallucination"] == 0
    unit = json.loads(json.dumps(g)); unit["fields"]["span"]["unit"] = "km"
    assert _score(unit, rec)["wrong"] == 1                      # a converted or altered unit is wrong, not close
    inv = _score(None, rec)
    assert not inv["valid"] and inv["miss"] == inv["fields_total"]


def test_hallucinating_a_value_the_brief_never_gave_is_counted():
    rec = next(r for r in SPLITS["test_iid"] if r["gold"]["intent"] == "design" and r["gold"]["fields"]["cover"] is None)
    pred = json.loads(json.dumps(rec["gold"])); pred["fields"]["cover"] = {"value": 30, "unit": "mm"}
    s = _score(pred, rec)
    assert s["hallucination"] == 1 and not s["exact"]


def test_intent_errors_are_classified():
    rec = next(r for r in ALL if r["gold"]["intent"] == "unsafe_request")
    assert _score({"intent": "design", "fields": {}}, rec)["intent_bad_allow"]
    good = _design_rec()
    assert _score({"intent": "out_of_scope", "fields": {}}, good)["intent_bad_block"]


def test_snapshot_rows_cover_the_image_cases():
    snaps = [r for r in ALL if r["family"] == "snapshot"]
    assert all(r["image_text"] and "<image_text>" in r["messages"][1]["content"] for r in snaps)
    blurry = [r for r in snaps if r["kind"] == "snapshot_blurry"]
    assert blurry and all(all(v is None for v in r["gold"]["fields"].values()) for r in blurry)
    assert all(r["gold"]["intent"] == "not_a_beam_brief" for r in snaps if r["kind"] == "snapshot_unrelated")
    assert any(r["gold"]["fields"]["span"] and r["gold"]["fields"]["span"]["unit"] not in r["text"] for r in snaps)   # value only in the image
    inj = [r for r in snaps if r["kind"] == "snapshot_injection"]
    assert inj and all(r["gold"]["fields"]["fck"] != 10 for r in inj)


def test_parse_accepts_fenced_and_wrapped_json():
    assert ev.parse('```json\n{"a": 1}\n```') == {"a": 1}
    assert ev.parse('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert ev.parse("no json here") is None


def test_local_backend_is_lazy_and_fails_with_the_pipelines_error_type():
    llm = LocalLLM()                                          # constructing it must not import torch
    assert llm.for_model("anything") is llm
    with pytest.raises(LLMError, match="images"):
        llm.generate("s", "u", images=[{"mime": "image/png", "data": "x"}])
    if importlib.util.find_spec("torch") is None:
        assert not llm.available
        with pytest.raises(LLMError, match="install torch"):
            llm.generate("s", "u", json_mode=True)
        assert llm.attempts[-1]["outcome"] == "error"


# ---------------------------------------------------------------- a model outage must not abort or distort an evaluation
def test_retry_recovers_then_gives_up(monkeypatch):
    monkeypatch.setattr(ev.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(rec):
        calls["n"] += 1
        if calls["n"] < 3:
            raise LLMError("503 busy")
        return "ok"
    assert ev.call_with_retry(flaky, {}) == ("ok", None)

    def down(rec):
        raise LLMError("HTTP 503 down")
    out, err = ev.call_with_retry(down, {})
    assert out == "" and "503" in err


def test_api_failures_are_skipped_not_scored_and_a_rerun_resumes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ev.time, "sleep", lambda s: None)
    rows = ev.load("test_iid")[:12]
    monkeypatch.setattr(ev, "load", lambda split: rows)
    bad, made = {rows[0]["id"]}, []

    def fake_backend(name, args):
        def fn(rec):
            made.append(rec["id"])
            if rec["id"] in bad:
                raise LLMError("HTTP 503 down")
            return json.dumps(rec["gold"])
        return fn
    monkeypatch.setattr(ev, "predictor", fake_backend)
    argv = ["intake_eval.py", "--backend", "gemini", "--split", "test_iid", "--cache", str(tmp_path / "c.jsonl"), "--out", str(tmp_path / "sub" / "o.jsonl")]
    monkeypatch.setattr(sys, "argv", argv)

    assert ev.main() == 0                                   # the outage did not crash the run
    out = capsys.readouterr().out
    assert "11 rows scored" in out and "1 skipped because the API failed" in out
    assert "row exact 100.0%" in out                        # the outage did not count against the model
    saved = [json.loads(line) for line in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert len(saved) == 11 and rows[0]["id"] not in {d["id"] for d in saved}
    assert (tmp_path / "sub" / "o.jsonl").exists()          # the output folder is created

    bad.clear(); made.clear()                               # the API is back: only the failed row is asked again
    assert ev.main() == 0
    assert made == [rows[0]["id"]]
    assert "12 rows scored" in capsys.readouterr().out


def test_missing_info_is_not_out_of_scope():
    from app.pipeline import _is_missing_info_refusal as f
    assert f(None, "Engineer: Design a beam for a 6 m span.")
    assert f("missing details", "Engineer: I want a beam for my house.")
    assert not f("T-beam", "Engineer: T-beam, 6 m span")      # a named unsupported feature is never overridden
    assert not f(None, "Engineer: what is the weather today")  # not about a beam

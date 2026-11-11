"""Tests for the benchmark tooling: metrics (A1) and pre-flight checks (A3)."""
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "benchmark"
pytestmark = pytest.mark.skipif(not BENCH.exists(), reason="benchmark/ not present")
if BENCH.exists():
    sys.path.insert(0, str(BENCH))
    import checks
    import guard_eval
    import metrics

G = ["BLOCK"] * 4 + ["ALLOW"] * 6


def test_perfect_guard():
    m = metrics.compute_metrics(G, list(G))
    assert m["accuracy"] == 1 and m["mcc"] == 1 and m["safety_rate"] == 1 and m["usability_rate"] == 1


def test_known_confusion_matrix():
    preds = ["BLOCK", "BLOCK", "BLOCK", "ALLOW"] + ["ALLOW"] * 5 + ["BLOCK"]   # 3 caught, 1 missed, 1 false block
    m = metrics.compute_metrics(G, preds)
    assert (m["false_allow"], m["false_block"]) == (1, 1)
    assert m["safety_rate"] == pytest.approx(0.75) and m["usability_rate"] == pytest.approx(5 / 6)
    assert m["mcc"] == pytest.approx((3 * 5 - 1 * 1) / ((3 + 1) * (3 + 1) * (5 + 1) * (5 + 1)) ** 0.5)


def test_refuse_everything_guard_scores_badly_on_usability():
    """The A1 acceptance check: a guard that blocks everything looks perfect on safety and terrible on usability."""
    m = metrics.compute_metrics(G, ["BLOCK"] * len(G))
    assert m["safety_rate"] == 1 and m["usability_rate"] == 0 and m["mcc"] == 0
    assert metrics.baselines(G)["always BLOCK"]["usability_rate"] == 0


def test_unknown_prediction_is_wrong_not_dropped():
    m = metrics.compute_metrics(["BLOCK", "ALLOW"], ["???", "ALLOW"])
    assert m["unknown"] == 1 and m["accuracy"] == 0.5 and m["false_allow"] == 0 and m["safety_rate"] == 0


def test_bootstrap_is_seeded_and_ordered():
    preds = list(G); preds[0] = "ALLOW"
    a, b = metrics.bootstrap_ci(G, preds, "accuracy", 300, 1), metrics.bootstrap_ci(G, preds, "accuracy", 300, 1)
    assert a == b and a[0] <= a[1]
    assert metrics.bootstrap_ci(["BLOCK"], ["BLOCK"]) is None


def test_format_report_lists_baselines():
    out = metrics.format_report("t", G, list(G), iters=50)
    assert "always ALLOW" in out and "MCC" in out and "gold BLOCK" in out


# --------------------------------------------------------------- pre-flight checks
def _case(**kw):
    base = {"id": "X01", "category": "golden", "mode": "chat", "brief": "Simply supported beam 6 m.", "expect": {"status": "designed"}}
    return {**base, **kw}


def test_model_view_hides_every_label():
    v = checks.model_view(_case(attachment="spec"))
    assert set(v) == {"text", "attachment"} and "expect" not in str(v) and "golden" not in str(v)


@pytest.mark.parametrize("brief,needle", [
    ("This beam is out_of_scope", "out_of_scope"), ("Case G01 beam, 6 m", "G01"), ("expected needs_info", "needs_info"),
])
def test_leaked_labels_are_errors(brief, needle):
    issues = checks.check_cases([_case(brief=brief)])
    assert any(i["severity"] == "error" and needle in i["message"] for i in issues)


def test_hygiene_errors():
    assert any("without a brief" in i["message"] for i in checks.check_cases([_case(brief="  ")]))
    assert any("duplicate case id" in i["message"] for i in checks.check_cases([_case(), _case()]))
    assert any("over the API limit" in i["message"] for i in checks.check_cases([_case(brief="x" * 8001)]))
    assert any("missing field" in i["message"] for i in checks.check_cases([{"id": "Y01", "mode": "chat", "brief": "b"}]))
    assert any("structured case" in i["message"] for i in checks.check_cases([_case(mode="structured", input=None)]))


def test_guard_cases_need_both_classes():
    one_sided = [{"id": f"S{i:02d}", "task": "scope", "gold": "ALLOW", "text": f"beam {i}"} for i in range(12)]
    assert any("no BLOCK cases" in i["message"] for i in checks.check_guard_cases(one_sided))
    assert any("unknown task" in i["message"] for i in checks.check_guard_cases([{"id": "Z1", "task": "x", "gold": "ALLOW", "text": "t"}]))


def test_real_case_files_pass_preflight():
    assert not [i for i in checks.check_cases(guard_eval.load_jsonl("cases.jsonl")) if i["severity"] == "error"]
    assert not [i for i in checks.check_guard_cases(guard_eval.load_jsonl("guard_cases.jsonl")) if i["severity"] == "error"]

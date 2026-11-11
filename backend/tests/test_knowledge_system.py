import pytest
from fastapi.testclient import TestClient

from app import main
from app.verifier import RULE_META


@pytest.fixture
def client():
    return TestClient(main.app)


def test_kb_structure(client):
    kb = client.get("/api/kb").json()
    topics = {t["id"] for t in kb["topics"]}
    ids = [e["id"] for e in kb["entries"]]
    assert kb["count"] == len(ids) >= 80
    assert len(ids) == len(set(ids))
    assert all(e["topic"] in topics and e["title"] and e["summary"] for e in kb["entries"])
    assert all(t["count"] > 0 for t in kb["topics"])
    assert sum(t["count"] for t in kb["topics"]) == kb["count"]


def test_kb_covers_key_subjects(client):
    text = " ".join(e["title"].lower() for e in client.get("/api/kb").json()["entries"])
    for word in ("concrete grades", "development length", "wind load", "seismic", "doubly reinforced", "retaining walls", "neural"):
        assert word in text


def test_system_counts_match_code(client):
    s = client.get("/api/system").json()
    assert s["summary"]["verifier_rules"] == len(RULE_META) == len(s["verifier_rules"])
    assert {r["rule_id"] for r in s["verifier_rules"]} == set(RULE_META)
    assert s["summary"]["facts"] == len(s["facts"]) > 20
    assert s["summary"]["meta_rules"] == len(s["meta_rules"]) >= 10


def test_facts_come_from_live_tables(client):
    from app.is456 import tables as T
    facts = {f["name"]: f["value"] for f in client.get("/api/system").json()["facts"]}
    assert f"{T.GAMMA_RC:g} kN/m3" == facts["Unit weight of reinforced concrete"]
    assert "Fe500: 0.46" in facts["xu,max / d by steel grade"]


def test_graph_is_consistent(client):
    s = client.get("/api/system").json()
    nodes = {n["id"] for n in s["nodes"]}
    layers = {l["id"] for l in s["layers"]}
    assert all(n["layer"] in layers for n in s["nodes"])
    assert all(e["source"] in nodes and e["target"] in nodes for e in s["edges"])
    assert set(s["main_path"]) <= nodes


def test_every_api_route_is_documented(client):
    documented = {i["path"] for i in client.get("/api/system").json()["interface"]}
    actual = {r.path for r in main.app.routes if r.path.startswith("/api/")}
    assert actual <= documented, actual - documented


# ------------------------------------------------------------ model selection
def test_five_model_options_and_no_env_model(client, monkeypatch):
    from app import config
    monkeypatch.setenv("GEMINI_MODELS", "something-from-env")
    h = client.get("/api/health").json()
    assert len(h["model_options"]) == 5 and h["default_model"] == h["model_options"][0]["id"]
    assert h["models"] == [m["id"] for m in h["model_options"]]
    assert "something-from-env" not in config.gemini_models()


def test_for_model_puts_choice_first_and_keeps_fallbacks():
    from app.llm.gemini import GeminiClient
    c = GeminiClient("k", ["a", "b", "c"])
    assert c.for_model("c").models == ["c", "a", "b"]
    assert c.for_model(None).models == ["a", "b", "c"]
    assert c.for_model("c") is not c  # per-request copy, so last_model is not shared between requests


def test_chat_and_design_pass_the_selected_model(client, monkeypatch, tmp_path):
    from app.audit import AuditLog
    from app.pipeline import Pipeline
    seen = []

    class Rec:
        name, available, last_model = "rec", True, "rec"
        def __init__(self, model=None): self.model = model
        def for_model(self, model): seen.append(model); return Rec(model)
        def generate(self, *a, **k): raise __import__("app.llm.gemini", fromlist=["LLMError"]).LLMError("offline")

    monkeypatch.setattr(main, "pipeline", Pipeline(Rec(), AuditLog(tmp_path / "m.db")))
    form = {"span": {"value": 6, "unit": "m"}, "support": "simply_supported", "b": {"value": 300, "unit": "mm"}, "D": {"value": 550, "unit": "mm"},
            "cover": {"value": 30, "unit": "mm"}, "fck": 25, "fy": 500, "dead_load": {"value": 15, "unit": "kN/m"},
            "live_load": {"value": 12, "unit": "kN/m"}, "exposure": "moderate"}
    chosen = main.config.gemini_models()[3]
    assert client.post(f"/api/design?model={chosen}", json=form).status_code == 200
    assert client.post(f"/api/chat?model={chosen}", json={"messages": [{"role": "user", "text": "beam"}]}).status_code == 200
    assert client.post("/api/design", json=form).status_code == 200
    assert seen == [chosen, chosen, None]


def test_unknown_model_is_rejected(client):
    assert client.post("/api/chat?model=not-a-model", json={"messages": [{"role": "user", "text": "x"}]}).status_code == 422
    assert client.get("/api/health?deep=true&model=nope").status_code == 422

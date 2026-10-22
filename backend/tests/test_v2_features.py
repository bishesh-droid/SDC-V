import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.audit import AuditLog
from app.explore import explore
from app.export import runs_csv
from app.guardrails.input import Quantity, RawIntake
from app.llm.gemini import GeminiClient, LLMError
from app.pipeline import Pipeline
from app.scope import scope
from app.security import RateLimiter
from tests.conftest import FakeLLM
from tests.test_pipeline_api import BRIEF, intake_json


def raw(**kw):
    base = dict(span=Quantity(value=6, unit="m"), support="simply_supported", b=Quantity(value=300, unit="mm"),
                D=Quantity(value=550, unit="mm"), cover=Quantity(value=30, unit="mm"), fck=25, fy=500,
                dead_load=Quantity(value=15, unit="kN/m"), live_load=Quantity(value=12, unit="kN/m"), exposure="moderate")
    base.update(kw)
    return RawIntake(**base)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "audit", AuditLog(tmp_path / "v2.db"))
    monkeypatch.setattr(main, "pipeline", Pipeline(None, main.audit))
    monkeypatch.setattr(main, "limiter", RateLimiter())
    monkeypatch.delenv("SDCV_API_TOKEN", raising=False)
    monkeypatch.delenv("RATE_LIMIT_PER_MIN", raising=False)
    return TestClient(main.app)


FORM = {"span": {"value": 6, "unit": "m"}, "support": "simply_supported", "b": {"value": 300, "unit": "mm"},
        "D": {"value": 550, "unit": "mm"}, "cover": {"value": 30, "unit": "mm"}, "fck": 25, "fy": 500,
        "dead_load": {"value": 15, "unit": "kN/m"}, "live_load": {"value": 12, "unit": "kN/m"}, "exposure": "moderate"}


# ----------------------------------------------------------- gemini client
class Resp:
    def __init__(self, code, payload=None, text=""):
        self.status_code, self._p, self.text = code, payload, text

    def json(self):
        if self._p is None:
            raise ValueError
        return self._p


OK = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}


def test_gemini_falls_through_to_next_model_and_reports_per_model_errors(monkeypatch):
    seen = []

    def post(url, **kw):
        seen.append(url)
        return Resp(404, {"error": {"message": "gone"}}) if "dead" in url else Resp(200, OK)

    monkeypatch.setattr(httpx, "post", post)
    c = GeminiClient("k", ["dead-1", "good"], timeout=5, budget=30)
    assert c.generate("s", "u") == "hello" and c.last_model == "good"
    assert c.last_errors["dead-1"].startswith("HTTP 404 gone")
    assert sum("dead-1" in u for u in seen) == 1  # 404 is not retried


def test_gemini_timeout_skips_model_without_retry(monkeypatch):
    calls = []

    def post(url, **kw):
        calls.append(url)
        if "slow" in url:
            raise httpx.ReadTimeout("t")
        return Resp(200, OK)

    monkeypatch.setattr(httpx, "post", post)
    c = GeminiClient("k", ["slow", "fast"], timeout=5, budget=30)
    assert c.generate("s", "u") == "hello"
    assert sum("slow" in u for u in calls) == 1 and "timed out" in c.last_errors["slow"]


def test_gemini_error_lists_every_model(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: Resp(404, {"error": {"message": "gone"}}))
    c = GeminiClient("k", ["a", "b", "c"], timeout=5, budget=30)
    with pytest.raises(LLMError) as e:
        c.generate("s", "u")
    assert all(m in str(e.value) for m in ("a:", "b:", "c:"))


def test_gemini_budget_stops_the_chain(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: Resp(404, {"error": {"message": "gone"}}))
    c = GeminiClient("k", ["a", "b"], timeout=5, budget=0.5)
    with pytest.raises(LLMError) as e:
        c.generate("s", "u")
    assert "budget" in str(e.value)


def test_probe_never_raises_without_key():
    assert GeminiClient("", ["a"]).probe()["ok"] is False


# ------------------------------------------------------------------ audit
def test_audit_stores_only_redacted_messages(tmp_path):
    audit = AuditLog(tmp_path / "a.db")
    llm = FakeLLM([intake_json(), "x"])
    res = Pipeline(llm, audit).run_chat([{"role": "user", "text": BRIEF + " Contact me at jane.doe@example.com"}])
    rec = audit.get(res.run_id)["record"]
    stored = rec["messages"][0]["text"]
    assert "jane.doe@example.com" not in stored and "[email]" in stored


def test_audit_search_filters_and_stats(tmp_path):
    a = AuditLog(tmp_path / "s.db")
    a.save("r1", "designed", "chat", "simply supported 6 m", {"result": {"narrative_source": "llm"}, "llm_model": "m1"})
    a.save("r2", "rejected", "structured", "cover problem", {"result": {}})
    a.save("r3", "designed", "structured", "cantilever 2 m", {"result": {"narrative_source": "template"}})
    a.review("r3", "Eng. A", "ok")
    assert a.search(status="designed")[1] == 2
    assert a.search(mode="chat")[1] == 1
    assert [r["id"] for r in a.search(q="cantilever")[0]] == ["r3"]
    assert a.search(reviewed=True)[1] == 1 and a.search(reviewed=False)[1] == 2
    assert a.search(q="%")[1] == 0  # wildcard characters are escaped, not interpreted
    assert a.search(limit=1, offset=1)[0][0]["id"] in ("r1", "r2", "r3")
    s = a.stats()
    assert s["total"] == 3 and s["by_status"]["designed"] == 2 and s["reviewed"] == 1
    assert s["models"] == {"m1": 1} and s["narrative_source"] == {"llm": 1, "template": 1}


def test_csv_neutralises_formula_injection():
    out = runs_csv([{"id": "x", "summary": "=HYPERLINK(1)", "status": "designed"}])
    assert "'=HYPERLINK(1)" in out


# --------------------------------------------------------------------- api
def test_runs_filter_total_header_and_validation(client):
    client.post("/api/design", json=FORM)
    client.post("/api/design", json={**FORM, "cover": {"value": 10, "unit": "mm"}})
    r = client.get("/api/runs", params={"status": "rejected"})
    assert r.headers["X-Total-Count"] == "1" and r.json()[0]["status"] == "rejected"
    assert client.get("/api/runs", params={"status": "bogus"}).status_code == 422
    assert client.get("/api/runs", params={"limit": 0}).status_code == 422
    assert client.get("/api/runs.csv").text.startswith("id,created_at,status")
    assert client.get("/api/stats").json()["total"] == 2


def test_report_markdown_export(client):
    rid = client.post("/api/design", json=FORM).json()["run_id"]
    r = client.get(f"/api/runs/{rid}/report.md")
    assert r.status_code == 200 and "## Verifier checks" in r.text and "DRAFT" in r.text
    assert client.get("/api/runs/nope/report.md").status_code == 404


def test_scope_matches_validation(client):
    s = client.get("/api/scope").json()
    assert s["limits"]["span_m"] == {"gt": 0, "le": 15} and s["limits"]["fck"] == [20, 25, 30, 35, 40]
    assert s["rule_count"] == len(client.get("/api/rules").json()) == 19
    assert scope()["out_of_scope"]


def test_explore_returns_sorted_scan_and_lightest(client):
    r = client.post("/api/explore", json=FORM).json()
    assert r["status"] == "ok" and r["scanned"] > 20
    areas = [x["concrete_area_mm2"] for x in r["rows"]]
    assert areas == sorted(areas)
    best = r["lightest_passing"]
    assert best and best["ok"] and all(not x["ok"] or x["concrete_area_mm2"] >= best["concrete_area_mm2"] for x in r["rows"])
    assert explore(raw(fck=None))["status"] == "needs_info"
    assert explore(raw(cover=Quantity(value=10, unit="mm")))["status"] == "rejected"


def test_token_auth_protects_api_but_not_health_or_page(client, monkeypatch):
    monkeypatch.setenv("SDCV_API_TOKEN", "s3cret")
    assert client.get("/api/health").json()["auth_required"] is True
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/runs", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/").status_code == 200


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    codes = [client.post("/api/design", json=FORM).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    r = client.post("/api/design", json=FORM)
    assert int(r.headers["Retry-After"]) >= 1
    assert client.get("/api/health").status_code == 200  # reads are not limited


def test_rate_limiter_window():
    rl = RateLimiter(window_s=0.2)
    assert [rl.check("k", 2) for _ in range(3)][2] > 0
    import time
    time.sleep(0.25)
    assert rl.check("k", 2) == 0 and rl.check("k", 0) == 0


def test_security_headers_and_static_whitelist(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/bg.js").status_code == 200 and client.get("/static/styles.css").status_code == 200
    assert client.get("/static/server.mjs").status_code == 404
    assert client.get("/static/package.json").status_code == 404


def test_deep_health_uses_probe(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main.llm, "probe", lambda: {"ok": True, "model": "m", "latency_ms": 5})
    monkeypatch.setattr(main.llm, "remote_models", lambda: ["m"])
    monkeypatch.setattr(main, "_probe_cache", {"at": 0.0, "value": None})
    h = client.get("/api/health", params={"deep": "true"}).json()
    assert h["llm"]["probe"]["ok"] and h["llm"]["unavailable_models"] == list(main.llm.models)
    assert client.get("/api/health", params={"deep": "true"}).json()["llm"]["cached"] is True

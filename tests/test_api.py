"""API + service-layer integration, fully offline: seed the store from the bulk
slice + Roe's real Pre-Primary summary, then exercise the endpoints."""
from conftest import seed_roe_store as _seed
from fastapi.testclient import TestClient


def _client():
    from guardian_contrib.api.app import app
    return TestClient(app)


def test_combined_endpoint_penny_accurate(temp_db):
    _seed()
    r = _client().get("/v1/committees/11932/combined")
    assert r.status_code == 200
    d = r.json()
    assert d["beginning"] == "29863.66"
    assert d["raised"] == "42750.00"
    assert d["loans"] == "0.00"
    assert d["expended"] == "4278.24"
    assert d["ending"] == "68335.42"
    assert d["continuing_raised"] == "33500.00"
    assert d["identity_ok"] is True
    assert "Ending omits continuing-period spending" in d["caveats"]


def test_summary_is_from_pdf_not_bulk(temp_db):
    _seed()
    d = _client().get("/v1/committees/11932/summary").json()
    assert d["summary"]["beginning"] == "29863.66"
    assert d["summary"]["raised_excl_loans"] == "9250.00"  # PP only, not combined


def test_continuing_endpoint(temp_db):
    _seed()
    d = _client().get("/v1/committees/11932/continuing").json()
    assert d["raised"] == "33500.00" and d["count"] == 12 and d["deduped"] is True


def test_candidates_and_flexible_query(temp_db):
    _seed()
    c = _client()
    cand = c.get("/v1/candidates", params={"name": "roe"}).json()
    assert cand["count"] >= 1
    q = c.post("/v1/query", json={"select": {"committee": "11932"}, "category": "combined"}).json()
    assert q["category"] == "combined" and q["data"][0]["ending"] == "68335.42"


def test_status_freshness(temp_db):
    _seed()
    d = _client().get("/v1/status").json()
    assert d["extract_as_of"]["max_receipt_date"] == "2026-06-15"
    assert d["changed_since_prev"] is True


def test_api_key_enforced(temp_db, monkeypatch):
    monkeypatch.setenv("GUARDIAN_API_KEYS", "secret1,secret2")
    import guardian_contrib.config as cfg
    cfg._settings = None
    _seed()
    c = _client()
    assert c.get("/v1/calendar").status_code == 401
    assert c.get("/v1/calendar", headers={"X-API-Key": "secret1"}).status_code == 200

"""The Public Ledger web UI renders (offline, seeded): dashboard, dossier, flags."""
from conftest import seed_roe_store
from fastapi.testclient import TestClient


def _client():
    from guardian_contrib.api.app import app
    return TestClient(app)


def test_dashboard_renders_with_real_figures(temp_db):
    seed_roe_store()
    r = _client().get("/")
    assert r.status_code == 200
    assert "The Money Ledger" in r.text
    assert "68,335.42" in r.text            # Roe combined ending, penny-accurate
    assert "/c/11932" in r.text             # links to the dossier


def test_dossier_renders(temp_db):
    seed_roe_store()
    r = _client().get("/c/11932")
    assert r.status_code == 200
    assert "ROE" in r.text and "68,335.42" in r.text
    assert "Continuing contributions" in r.text


def test_flags_page_renders(temp_db):
    seed_roe_store()
    assert _client().get("/flags").status_code == 200


def test_unknown_committee_is_404(temp_db):
    seed_roe_store()
    assert _client().get("/c/000000").status_code == 404


def test_static_assets_served(temp_db):
    seed_roe_store()
    c = _client()
    assert c.get("/static/ledger.css").status_code == 200
    assert c.get("/static/app.js").status_code == 200

"""HTML routes for the Public Ledger UI. Calls the service layer directly."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import service
from . import charts
from .format import register

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
register(templates.env)
charts.register(templates.env)

# Cache-bust static assets by their newest mtime (fresh on every edit; stable in prod).
templates.env.globals["asset_v"] = lambda: str(
    int(max((p.stat().st_mtime for p in (_DIR / "static").glob("*")), default=0)))

router = APIRouter(include_in_schema=False)
static = StaticFiles(directory=str(_DIR / "static"))


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, q: str | None = None):
    data = service.dashboard_overview()
    org_ids = [r["org_id"] for r in data["rows"] if r["org_id"]]
    series = service.series_for_orgs(org_ids)
    race = sorted(((r["candidate"], r["raised_cents"]) for r in data["rows"] if r["raised_cents"] > 0),
                  key=lambda x: -x[1])[:12]
    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"data": data, "series": series, "race": race, "active": "dashboard", "q": q})


@router.get("/c/{org_id}", response_class=HTMLResponse)
def candidate(request: Request, org_id: str):
    try:
        d = service.candidate_dossier(org_id)
    except service.NotFound:
        return HTMLResponse(
            "<p style='font-family:sans-serif;padding:40px'>Committee not found. "
            "<a href='/'>← Roster</a></p>", status_code=404)
    return templates.TemplateResponse(
        request=request, name="candidate.html",
        context={"d": d, "active": "dashboard", "q": None})


@router.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str | None = None):
    results = (service.search_candidates(name=q) if q and q.strip()
               else {"candidates": [], "count": 0, "as_of": {}})
    return templates.TemplateResponse(
        request=request, name="search.html",
        context={"results": results, "q": q, "active": None})


@router.get("/flags", response_class=HTMLResponse)
def flags(request: Request):
    data = service.dashboard_overview()
    groups: dict[str, list] = {"high": [], "warn": [], "info": []}
    for r in data["rows"]:
        for f in r["flags"]:
            groups.setdefault(f["severity"], []).append({"row": r, "flag": f})
    return templates.TemplateResponse(
        request=request, name="flags.html",
        context={"data": data, "groups": groups, "active": "flags", "q": None})

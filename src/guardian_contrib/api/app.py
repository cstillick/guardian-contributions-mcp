"""FastAPI app. Base path /v1. Auth via X-API-Key (disabled when no keys set —
local single-user). All money serialized as decimal strings; every response
carries the extract as-of."""
from __future__ import annotations

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import service
from ..config import get_settings
from ..db import init_db

app = FastAPI(
    title="Guardian Contributions API",
    version="0.1.0",
    description="Oklahoma Ethics 'Guardian' combined Pre-Primary + Continuing reporting.",
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    keys = get_settings().api_keys
    if keys and x_api_key not in keys:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@app.exception_handler(service.NotFound)
def _not_found(_request, exc: service.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


auth = [Depends(require_api_key)]
V1 = "/v1"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"service": "guardian-contributions", "version": "0.1.0", "docs": "/docs"}


# ---- Axis A: resolution & race -----------------------------------------
@app.get(V1 + "/candidates", dependencies=auth)
def candidates(name: str | None = None, district: str | None = None,
               office: str | None = None, party: str | None = None,
               cycle: str | None = None, year: int | None = None):
    return service.search_candidates(name, district, office, party, cycle, year)


@app.get(V1 + "/committees/{org_id}", dependencies=auth)
def committee(org_id: str):
    return service.get_committee(org_id)


@app.get(V1 + "/districts/{district}/candidates", dependencies=auth)
def district_candidates(district: str, year: int | None = None):
    return service.district_candidates(district, year)


# ---- Axis B: filings & reports -----------------------------------------
@app.get(V1 + "/committees/{org_id}/filings", dependencies=auth)
def filings(org_id: str):
    return service.list_filings(org_id)


@app.get(V1 + "/reports/{filing_id}", dependencies=auth)
def report(filing_id: str):
    return service.get_report(filing_id)


# ---- Axis B: financials -------------------------------------------------
@app.get(V1 + "/committees/{org_id}/summary", dependencies=auth)
def summary(org_id: str):
    return service.get_summary(org_id)


@app.get(V1 + "/contributions", dependencies=auth)
def contributions(org_id: str | None = None, district: str | None = None,
                  date_from: str | None = None, date_to: str | None = None,
                  type: str | None = None, min_amount: float | None = None,
                  dedup: bool = True, year: int | None = None):
    return service.get_contributions(org_id, district, date_from, date_to,
                                     type, min_amount, dedup, year)


@app.get(V1 + "/committees/{org_id}/continuing", dependencies=auth)
def continuing(org_id: str, date_from: str | None = None, date_to: str | None = None,
               year: int | None = None):
    return service.get_continuing(org_id, date_from, date_to, year)


@app.get(V1 + "/committees/{org_id}/combined", dependencies=auth)
def combined(org_id: str, year: int | None = None):
    return service.get_combined(org_id, year)


@app.get(V1 + "/districts/{district}/combined", dependencies=auth)
def district_combined(district: str, year: int | None = None):
    return service.district_combined(district, year)


# ---- calendar / flags / status -----------------------------------------
@app.get(V1 + "/calendar", dependencies=auth)
def calendar(year: int | None = None):
    return service.get_calendar(year)


@app.get(V1 + "/flags", dependencies=auth)
def flags(district: str | None = None, org_id: str | None = None, year: int | None = None):
    return service.get_flags(district, org_id, year)


@app.get(V1 + "/status", dependencies=auth)
def status(year: int | None = None):
    return service.refresh_status(year)


# ---- flexible category query -------------------------------------------
class QueryBody(BaseModel):
    select: dict = {}
    category: str
    window: dict | None = None
    options: dict | None = None
    year: int | None = None


@app.post(V1 + "/query", dependencies=auth)
def query(body: QueryBody):
    return service.query(body.select, body.category, body.window, body.options, body.year)


# ---- refresh ------------------------------------------------------------
class RefreshBody(BaseModel):
    year: int | None = None
    enrich_roster: bool = True


@app.post(V1 + "/refresh", dependencies=auth, status_code=202)
def refresh(body: RefreshBody, background: BackgroundTasks):
    from ..ingest.runner import ingest_run
    background.add_task(ingest_run, year=body.year, enrich_roster=body.enrich_roster)
    return {"accepted": True, "year": body.year or get_settings().default_cycle_year,
            "note": "ingestion started in background; poll /v1/status"}


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

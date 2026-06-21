"""Guardian Contributions MCP server (stdio).

Exposes the two selection axes from the design spec:
  Axis A (who/where): candidate · committee · district · office · party · cycle
  Axis B (what):      summary · combined · continuing · contributions · loans ·
                      report · filing_history · flags

Focused tools (5A) are the primary surface; `query` (5B) is the explicit
category selector for the long tail. Every tool reads the normalized store via
the shared service layer — Guardian is never touched on the request path.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .. import service
from ..config import get_settings
from ..roster import ROSTER_2026

mcp = FastMCP("guardian-contributions")


# ---- Axis A — politician / race ----------------------------------------
@mcp.tool()
def search_candidates(name: str | None = None, district: str | None = None,
                      office: str | None = None, party: str | None = None,
                      cycle: str | None = None, year: int | None = None) -> dict:
    """Resolve candidates to committees (Org IDs). Never fuzzy-matches: returns all
    matches and flags `has_multiple_committees` so the caller picks the regular-cycle
    one. Filter by name, district (HD-42/SD-15), office, party ((D)/(R)), or cycle."""
    return service.search_candidates(name, district, office, party, cycle, year)


@mcp.tool()
def get_committee(org_id: str) -> dict:
    """Committee detail by Org ID (Ethics #), including any OTHER committees the
    same candidate has (surfaces Special-vs-General — Rule 6)."""
    return service.get_committee(org_id)


@mcp.tool()
def list_district_candidates(district: str, year: int | None = None) -> dict:
    """Every candidate/committee in a House/Senate district (whole-race rollup)."""
    return service.district_candidates(district, year)


# ---- Axis A×B — filings -------------------------------------------------
@mcp.tool()
def list_filings(org_id: str) -> dict:
    """All reports a committee filed (type, period, amended), newest-first."""
    return service.list_filings(org_id)


@mcp.tool()
def get_report(filing_id: str) -> dict:
    """One filed report's parsed Schedule Summary (Reporting-Period column)."""
    return service.get_report(filing_id)


# ---- Axis B — financial / contribution ---------------------------------
@mcp.tool()
def get_summary(org_id: str) -> dict:
    """Pre-Primary / periodic figures (Beginning, Raised excl-loans, Loans, Expended,
    Ending). ALWAYS from the parsed report PDF — never re-summed from bulk (Rule 3)."""
    return service.get_summary(org_id)


@mcp.tool()
def get_contributions(org_id: str | None = None, district: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      receipt_type: str | None = None, min_amount: float | None = None,
                      dedup: bool = True, year: int | None = None) -> dict:
    """Itemized receipts + totals for a committee or a whole district. Optional
    window (date_from/date_to ISO), receipt_type, and min_amount filters."""
    return service.get_contributions(org_id, district, date_from, date_to,
                                     receipt_type, min_amount, dedup, year)


@mcp.tool()
def get_continuing(org_id: str, date_from: str | None = None,
                   date_to: str | None = None, year: int | None = None) -> dict:
    """Deduped continuing-window total (Raised vs Loans split), counting each receipt
    once across however many continuing reports were filed (Appendix C / Rule 2).
    Defaults to the cycle's computed continuing window."""
    return service.get_continuing(org_id, date_from, date_to, year)


@mcp.tool()
def get_combined(org_id: str | None = None, district: str | None = None,
                 year: int | None = None) -> dict:
    """The headline number: Pre-Primary base + Continuing layered on top, for one
    committee (org_id) or every candidate in a district. Recomputes Ending =
    Beginning + Raised + Loans − Expended; note: Ending omits continuing-period spend."""
    if district and not org_id:
        return service.district_combined(district, year)
    if not org_id:
        raise ValueError("provide org_id or district")
    return service.get_combined(org_id, year)


@mcp.tool()
def get_flags(district: str | None = None, org_id: str | None = None,
              year: int | None = None) -> dict:
    """Computed alerts: large-loan self-dealing (loan ≥ raised), sub-$1,000
    continuing receipts, amended-report-used, multiple committees, no Pre-Primary,
    no committee found, identity mismatches."""
    return service.get_flags(district, org_id, year)


# ---- calendar / status / flexible query --------------------------------
@mcp.tool()
def get_calendar(year: int | None = None) -> dict:
    """The cycle's reporting calendar: primary date (3rd Tue of June), Pre-Primary
    period, and continuing window — computed, not hardcoded (Rule 1)."""
    return service.get_calendar(year)


@mcp.tool()
def refresh_status(year: int | None = None) -> dict:
    """Extract as-of (max Filed/Receipt date) and whether it changed since the prior
    pull — so an identical re-pull is reported as 'no change' (Rule 13), not a fake update."""
    return service.refresh_status(year)


@mcp.tool()
def query(select: dict, category: str, window: dict | None = None,
          options: dict | None = None, year: int | None = None) -> dict:
    """Flexible category selector — pick {who/where} × {what} in one call.

    select: any of candidate, committee (Org ID), district, office, party, cycle.
    category: summary | combined | continuing_total | contributions | loans |
              report | filing_history | flags.
    window: {from, to} ISO dates (optional; defaults to the calendar).
    options: {dedup, min_amount, include_amended}.
    Returns a uniform envelope {as_of, selection, category, data, caveats}."""
    return service.query(select, category, window, options, year)


# ---- resources ----------------------------------------------------------
@mcp.resource("guardian://calendar/{year}")
def calendar_resource(year: str) -> str:
    return json.dumps(service.get_calendar(int(year)), indent=2)


@mcp.resource("guardian://status")
def status_resource() -> str:
    return json.dumps(service.refresh_status(), indent=2)


@mcp.resource("guardian://roster/{year}")
def roster_resource(year: str) -> str:
    return json.dumps({"year": int(year), "roster": ROSTER_2026}, indent=2)


def main() -> None:
    get_settings()  # validate config early
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()

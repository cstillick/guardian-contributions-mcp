"""Ingestion orchestration — a full run (Section 3-7).

Order: bulk extract -> committees + receipts -> freshness gate -> calendar ->
sequential per-roster-committee report enrichment (Rule 4) -> flags -> run log.

Report PDF fetches are SEQUENTIAL on purpose (session-state collision, Rule 4).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import asdict, dataclass

from sqlalchemy import delete, insert, select

from ..config import Settings, get_settings
from ..db import init_db, session_scope
from ..models import Committee, Flag, Receipt, Report, Run, Summary
from ..reporting_calendar import ReportingCalendar, build_calendar
from ..roster import all_roster_candidates, norm_name, resolve_org_id
from ..compute import flags as flagmod
from ..compute.continuing import continuing_total, query_window_receipts
from . import bulk as bulkmod
from .guardian_client import GuardianClient
from .reports import classify_report, parse_schedule_summary, pdf_text

_RECEIPT_COLS = ("cycle_year", "receipt_id", "org_id", "date", "amount_cents",
                 "receipt_type", "source_type", "source_name", "city", "state",
                 "zip", "filed_date", "amended", "description")


@dataclass
class BulkStats:
    extract_rows: int
    receipts: int
    committees: int
    malformed: int
    max_filed_date: dt.date | None
    max_receipt_date: dt.date | None


def build_name_index(records) -> dict[str, list[str]]:
    """{normalized candidate name -> [distinct org_ids]} from the extract (Rule 5)."""
    idx: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r.candidate_name:
            idx[norm_name(r.candidate_name)].add(r.org_id)
    return {k: sorted(v) for k, v in idx.items()}


def run_bulk_ingest(session, text: str, cycle_year: int) -> BulkStats:
    header, idx, rows, bad = bulkmod.parse_extract(text)
    records = list(bulkmod.iter_receipts(rows, idx, cycle_year))

    # Distinct committees from the extract (insert-if-missing).
    committees: dict[str, dict] = {}
    for r in records:
        if r.org_id not in committees:
            committees[r.org_id] = {
                "org_id": r.org_id,
                "legal_name": r.committee_name,
                "candidate_name": r.candidate_name or None,
                "committee_type": r.committee_type or None,
                "cycle_year": cycle_year,
            }
    existing = set(session.scalars(select(Committee.org_id)))
    new_comms = [c for oid, c in committees.items() if oid not in existing]
    if new_comms:
        session.execute(insert(Committee), new_comms)

    # Receipts: full snapshot — replace this cycle's rows.
    session.execute(delete(Receipt).where(Receipt.cycle_year == cycle_year))
    if records:
        session.execute(
            insert(Receipt),
            [{c: getattr(r, c) for c in _RECEIPT_COLS} for r in records],
        )

    max_filed, max_receipt = bulkmod.freshness(rows, idx)
    return BulkStats(
        extract_rows=len(rows), receipts=len(records), committees=len(committees),
        malformed=bad, max_filed_date=max_filed, max_receipt_date=max_receipt,
    )


def enrich_committee(
    session, client: GuardianClient, org_id: str, cycle_year: int,
    report_regex: str = r"PRE-PRIMARY",
) -> dict:
    """Fetch committee detail + the target periodic report; store report+summary.
    Rule 7: reject a report whose year != cycle_year. Returns an info dict."""
    info: dict = {"org_id": org_id, "report_stored": False, "rejected": None,
                  "version_count": 0, "continuing_reports": 0, "district": None}

    detail = client.committee_detail(org_id)
    comm = session.get(Committee, org_id)
    if comm is None:
        comm = Committee(org_id=org_id)
        session.add(comm)
    comm.legal_name = detail.legal_name or comm.legal_name
    comm.district = detail.district or comm.district
    comm.office = detail.office or comm.office
    comm.party = detail.party or comm.party
    comm.election_cycle = detail.election or comm.election_cycle
    comm.status = detail.status or comm.status
    comm.is_regular_cycle = detail.is_regular_cycle
    if detail.cycle_year:
        comm.cycle_year = detail.cycle_year
    info["district"] = comm.district

    filings = client.list_filings(org_id)
    info["continuing_reports"] = sum(1 for f in filings if classify_report(f.label) == "itemized")

    rf = client.fetch_report(org_id, report_regex)
    if rf is None:
        return info
    summary = parse_schedule_summary(pdf_text(rf.pdf))
    info["version_count"] = rf.version_count
    if summary.report_year is not None and summary.report_year != cycle_year:
        info["rejected"] = f"report_year {summary.report_year} != cycle {cycle_year}"
        return info  # Rule 7: wrong-cycle PDF rejected

    # Cache PDF and store report + summary.
    s = get_settings()
    s.pdf_cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = s.pdf_cache_dir / f"{org_id}_{rf.filing_id or 'pp'}.pdf"
    pdf_path.write_bytes(rf.pdf)

    if rf.filing_id:
        rep = session.get(Report, rf.filing_id) or Report(filing_id=rf.filing_id)
        rep.org_id = org_id
        rep.cycle_year = cycle_year
        rep.report_type = rf.label
        rep.report_class = classify_report(rf.label)
        rep.period_start = summary.period_start
        rep.period_end = summary.period_end
        rep.amended = summary.amended
        rep.is_latest_version = True
        rep.source_pdf_path = str(pdf_path)
        session.add(rep)
        session.flush()
        smry = session.get(Summary, rf.filing_id) or Summary(filing_id=rf.filing_id)
        smry.beginning_cents = summary.beginning_cents
        smry.total_received_cents = summary.total_received_cents
        smry.loans_cents = summary.loans_cents
        smry.expended_cents = summary.expended_cents
        smry.ending_cents = summary.ending_cents
        session.add(smry)
        info["report_stored"] = True
    if comm.district is None and summary.district:
        comm.district = (f"HD-{summary.district}" if comm.office and "REPRESENT" in comm.office.upper()
                         else summary.district)
    return info


def ingest_run(
    year: int | None = None,
    enrich_roster: bool = True,
    client: GuardianClient | None = None,
    bulk_text: str | None = None,
) -> dict:
    """Full run. Pass bulk_text/client to inject (tests); else fetch live."""
    settings = get_settings()
    year = year or settings.default_cycle_year
    init_db()
    owns_client = False
    if client is None and (enrich_roster or bulk_text is None):
        client = GuardianClient(settings)
        owns_client = True

    try:
        if bulk_text is None:
            bulk_text = bulkmod.unzip_to_text(client.download_bulk(year))

        with session_scope() as session:
            prev = session.scalars(
                select(Run).where(Run.cycle_year == year).order_by(Run.run_id.desc())
            ).first()
            stats = run_bulk_ingest(session, bulk_text, year)

            changed = not (
                prev is not None
                and prev.max_filed_date == stats.max_filed_date
                and prev.max_receipt_date == stats.max_receipt_date
            )

            cal = _calendar_for(session, year, stats)
            run = Run(
                started_at=dt.datetime.utcnow(), cycle_year=year,
                max_filed_date=stats.max_filed_date, max_receipt_date=stats.max_receipt_date,
                primary_date=cal.primary_date, pre_primary_start=cal.pre_primary_start,
                pre_primary_end=cal.pre_primary_end, continuing_start=cal.continuing_start,
                continuing_end=cal.continuing_end, extract_rows=stats.extract_rows,
                changed_since_prev=changed,
                note=("re-pull matched prior extract exactly; no figures changed"
                      if not changed else None),
            )
            session.add(run)
            session.flush()

            enriched = []
            if enrich_roster and client is not None:
                enriched = _enrich_and_flag(session, client, year, cal, run.run_id)

            return {
                "run_id": run.run_id, "year": year, "changed_since_prev": changed,
                "stats": asdict(stats), "calendar": cal.to_dict(),
                "enriched": len(enriched),
            }
    finally:
        if owns_client and client is not None:
            client.close()


def _calendar_for(session, year: int, stats: BulkStats) -> ReportingCalendar:
    """Prefer a stored Pre-Primary report's period (Rule 3); else documented default."""
    pp = session.scalars(
        select(Report).where(Report.cycle_year == year, Report.report_class == "periodic")
        .where(Report.period_start.is_not(None))
    ).first()
    period = (pp.period_start, pp.period_end) if pp and pp.period_end else None
    return build_calendar(year, pre_primary_period=period)


def _enrich_and_flag(session, client, year, cal, run_id) -> list[dict]:
    name_index = build_name_index(query_all_records(session, year))
    out = []
    for district, name in all_roster_candidates():
        res = resolve_org_id(name, name_index)
        if res["org_id"] is None:
            if res["source"] == "no_committee":
                _add_flag(session, run_id, flagmod.no_committee_found(name))
            elif res["multiple"]:
                _add_flag(session, run_id, flagmod.multiple_committees(
                    None, name, res["candidates"]))
            continue
        org_id = res["org_id"]
        try:
            info = enrich_committee(session, client, org_id, year)
        except Exception as e:  # network hiccup on one committee shouldn't kill the run
            _add_flag(session, run_id, flagmod.identity_mismatch(
                org_id, name, f"enrich failed: {e!r}"))
            continue
        _compute_committee_flags(session, run_id, org_id, name, year, cal, info)
        out.append({"name": name, "district": district, **info})
    return out


def query_all_records(session, year):
    """Lightweight receipt rows for name-index building."""
    return session.scalars(select(Receipt).where(Receipt.cycle_year == year)).all()


def _compute_committee_flags(session, run_id, org_id, name, year, cal, info):
    summary = None
    rep = session.scalars(
        select(Report).where(Report.org_id == org_id, Report.report_class == "periodic")
    ).first()
    if rep is not None:
        summary = session.get(Summary, rep.filing_id)

    receipts = query_window_receipts(session, org_id, year, cal.continuing_start, cal.continuing_end)
    cont = continuing_total(receipts, cal.continuing_start, cal.continuing_end)
    pp_raised = (summary.raised_excl_loans_cents or 0) if summary else 0
    pp_loans = (summary.loans_cents or 0) if summary else 0
    raised = pp_raised + cont.raised_cents
    loans = pp_loans + cont.loans_cents

    for f in (
        flagmod.large_loan(org_id, name, raised, loans),
        flagmod.amended_report_used(org_id, name, info.get("version_count", 0)),
        (flagmod.no_pre_primary(org_id, name) if summary is None else None),
    ):
        if f:
            _add_flag(session, run_id, f)
    for f in flagmod.sub_threshold(org_id, name, receipts, cal.continuing_start, cal.continuing_end):
        _add_flag(session, run_id, f)


def _add_flag(session, run_id, flag: dict):
    session.add(Flag(run_id=run_id, **flag))


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Run a Guardian ingestion.")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--no-reports", action="store_true", help="bulk only; skip report fetches")
    args = ap.parse_args()
    result = ingest_run(year=args.year, enrich_roster=not args.no_reports)
    import json
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

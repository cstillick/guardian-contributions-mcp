"""Service layer — the single place the rules are applied on read. Both the REST
API and the MCP server call these functions, so the two never diverge.

Every function opens its own session, returns plain JSON-able dicts (detached from
ORM), and stamps the extract as-of where relevant (Rule 10).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from .config import get_settings
from .db import session_scope
from .compute.combined import build_combined
from .compute.continuing import ContinuingTotal, continuing_total, query_window_receipts
from .compute import flags as flagmod
from .models import Committee, Flag, Receipt, Report, Run, Summary
from .money import decimal_str
from .reporting_calendar import ReportingCalendar, build_calendar


class NotFound(Exception):
    pass


# ---- shared helpers -----------------------------------------------------
def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    if isinstance(s, dt.date):
        return s
    return dt.date.fromisoformat(s)


def _latest_run(session, year: int) -> Run | None:
    return session.scalars(
        select(Run).where(Run.cycle_year == year).order_by(Run.run_id.desc())
    ).first()


def active_calendar(session, year: int) -> ReportingCalendar:
    run = _latest_run(session, year)
    if run and run.pre_primary_end and run.primary_date:
        return ReportingCalendar(
            year=year, primary_date=run.primary_date,
            pre_primary_start=run.pre_primary_start, pre_primary_end=run.pre_primary_end,
            continuing_start=run.continuing_start, continuing_end=run.continuing_end,
        )
    return build_calendar(year)


def as_of(session, year: int) -> dict:
    run = _latest_run(session, year)
    if not run:
        return {"max_filed_date": None, "max_receipt_date": None,
                "changed_since_prev": None, "last_run": None}
    return {
        "max_filed_date": run.max_filed_date.isoformat() if run.max_filed_date else None,
        "max_receipt_date": run.max_receipt_date.isoformat() if run.max_receipt_date else None,
        "changed_since_prev": run.changed_since_prev,
        "last_run": run.started_at.isoformat() if run.started_at else None,
    }


def _committee_card(c: Committee) -> dict:
    return {
        "org_id": c.org_id, "legal_name": c.legal_name, "candidate_name": c.candidate_name,
        "committee_type": c.committee_type, "district": c.district, "office": c.office,
        "party": c.party, "election": c.election_cycle, "cycle_year": c.cycle_year,
        "status": c.status, "is_regular_cycle": c.is_regular_cycle,
    }


def _summary_for_org(session, org_id: str) -> tuple[Report | None, Summary | None]:
    rep = session.scalars(
        select(Report).where(Report.org_id == org_id, Report.report_class == "periodic")
        .order_by(Report.period_end.desc())
    ).first()
    return (rep, session.get(Summary, rep.filing_id)) if rep else (None, None)


# ---- Axis A: resolution & race -----------------------------------------
def search_candidates(name=None, district=None, office=None, party=None,
                      cycle=None, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        q = select(Committee).where(Committee.cycle_year == year) if year else select(Committee)
        if name:
            like = f"%{name.lower()}%"
            from sqlalchemy import func, or_
            q = q.where(or_(func.lower(Committee.candidate_name).like(like),
                            func.lower(Committee.legal_name).like(like)))
        if district:
            q = q.where(Committee.district == district)
        if office:
            q = q.where(Committee.office.ilike(f"%{office}%"))
        if party:
            q = q.where(Committee.party == party)
        comms = list(s.scalars(q.limit(200)))
        # multiple-committee detection by candidate name
        by_name: dict[str, int] = {}
        for c in comms:
            by_name[(c.candidate_name or "").lower()] = by_name.get((c.candidate_name or "").lower(), 0) + 1
        cards = []
        for c in comms:
            card = _committee_card(c)
            card["has_multiple_committees"] = by_name.get((c.candidate_name or "").lower(), 0) > 1
            cards.append(card)
        return {"as_of": as_of(s, year), "count": len(cards), "candidates": cards}


def get_committee(org_id: str, year=None) -> dict:
    with session_scope() as s:
        c = s.get(Committee, org_id)
        if not c:
            raise NotFound(f"committee {org_id}")
        others = []
        if c.candidate_name:
            others = [oc.org_id for oc in s.scalars(
                select(Committee).where(Committee.candidate_name == c.candidate_name,
                                        Committee.org_id != org_id))]
        card = _committee_card(c)
        card["other_committees"] = others
        return card


def district_candidates(district: str, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        comms = list(s.scalars(select(Committee).where(Committee.district == district)))
        return {"district": district, "as_of": as_of(s, year),
                "candidates": [_committee_card(c) for c in comms]}


# ---- Axis B: filings & reports -----------------------------------------
def list_filings(org_id: str) -> dict:
    with session_scope() as s:
        reps = list(s.scalars(select(Report).where(Report.org_id == org_id)
                              .order_by(Report.period_end.desc())))
        return {"org_id": org_id, "filings": [
            {"filing_id": r.filing_id, "report_type": r.report_type,
             "report_class": r.report_class,
             "period_start": r.period_start.isoformat() if r.period_start else None,
             "period_end": r.period_end.isoformat() if r.period_end else None,
             "amended": r.amended, "is_latest_version": r.is_latest_version}
            for r in reps]}


def get_report(filing_id: str) -> dict:
    with session_scope() as s:
        r = s.get(Report, filing_id)
        if not r:
            raise NotFound(f"report {filing_id}")
        sm = s.get(Summary, filing_id)
        summary = None
        if sm:
            summary = {
                "beginning": decimal_str(sm.beginning_cents),
                "total_received": decimal_str(sm.total_received_cents),
                "loans": decimal_str(sm.loans_cents),
                "expended": decimal_str(sm.expended_cents),
                "ending": decimal_str(sm.ending_cents),
                "raised_excl_loans": decimal_str(sm.raised_excl_loans_cents),
            }
        return {
            "filing_id": r.filing_id, "org_id": r.org_id, "report_type": r.report_type,
            "report_class": r.report_class, "amended": r.amended,
            "period": {"start": r.period_start.isoformat() if r.period_start else None,
                       "end": r.period_end.isoformat() if r.period_end else None},
            "summary": summary, "source_pdf_path": r.source_pdf_path,
        }


# ---- Axis B: financials -------------------------------------------------
def get_summary(org_id: str) -> dict:
    """Pre-Primary/periodic figures — ALWAYS from a parsed PDF, never bulk re-sum (Rule 3)."""
    with session_scope() as s:
        rep, sm = _summary_for_org(s, org_id)
        if not sm:
            return {"org_id": org_id, "summary": None,
                    "note": "No periodic (Pre-Primary) report parsed yet for this committee"}
        return {
            "org_id": org_id, "filing_id": rep.filing_id, "report_type": rep.report_type,
            "period": {"start": rep.period_start.isoformat() if rep.period_start else None,
                       "end": rep.period_end.isoformat() if rep.period_end else None},
            "summary": {
                "beginning": decimal_str(sm.beginning_cents),
                "total_received": decimal_str(sm.total_received_cents),
                "loans": decimal_str(sm.loans_cents),
                "expended": decimal_str(sm.expended_cents),
                "ending": decimal_str(sm.ending_cents),
                "raised_excl_loans": decimal_str(sm.raised_excl_loans_cents),
            },
            "identity_ok": (sm.beginning_cents is not None and sm.ending_cents is not None
                            and sm.beginning_cents + (sm.total_received_cents or 0)
                            - (sm.expended_cents or 0) == sm.ending_cents),
        }


def get_contributions(org_id=None, district=None, date_from=None, date_to=None,
                      receipt_type=None, min_amount=None, dedup=True, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    start, end = _parse_date(date_from), _parse_date(date_to)
    min_cents = int(round(float(min_amount) * 100)) if min_amount is not None else None
    with session_scope() as s:
        org_ids = [org_id] if org_id else None
        if district and not org_id:
            org_ids = [c.org_id for c in s.scalars(
                select(Committee).where(Committee.district == district))]
        q = select(Receipt).where(Receipt.cycle_year == year)
        if org_ids is not None:
            q = q.where(Receipt.org_id.in_(org_ids))
        if start:
            q = q.where(Receipt.date >= start)
        if end:
            q = q.where(Receipt.date <= end)
        if receipt_type:
            q = q.where(Receipt.receipt_type == receipt_type)
        if min_cents is not None:
            q = q.where(Receipt.amount_cents >= min_cents)
        rows = list(s.scalars(q.order_by(Receipt.date)))
        seen, items, raised, loans = set(), [], 0, 0
        for r in rows:
            if dedup and r.receipt_id in seen:
                continue
            seen.add(r.receipt_id)
            items.append({
                "receipt_id": r.receipt_id, "org_id": r.org_id,
                "date": r.date.isoformat() if r.date else None,
                "amount": decimal_str(r.amount_cents), "receipt_type": r.receipt_type,
                "source_type": r.source_type, "source_name": r.source_name,
                "city": r.city, "state": r.state, "amended": r.amended,
            })
            if (r.amended or "").upper() != "Y":
                if r.receipt_type == "Loan":
                    loans += r.amount_cents
                else:
                    raised += r.amount_cents
        return {
            "as_of": as_of(s, year),
            "window": {"from": date_from, "to": date_to},
            "totals": {"raised": decimal_str(raised), "loans": decimal_str(loans),
                       "count": len(items)},
            "items": items,
        }


def get_continuing(org_id: str, date_from=None, date_to=None, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        cal = active_calendar(s, year)
        start = _parse_date(date_from) or cal.continuing_start
        end = _parse_date(date_to) or cal.continuing_end
        receipts = query_window_receipts(s, org_id, year, start, end)
        ct = continuing_total(receipts, start, end)
        return {
            "org_id": org_id, "as_of": as_of(s, year),
            "window": {"from": start.isoformat(), "to": end.isoformat()},
            "raised": decimal_str(ct.raised_cents), "loans": decimal_str(ct.loans_cents),
            "count": ct.count, "duplicates": ct.duplicates, "deduped": True,
        }


def get_combined(org_id: str, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        cal = active_calendar(s, year)
        rep, sm = _summary_for_org(s, org_id)
        receipts = query_window_receipts(s, org_id, year, cal.continuing_start, cal.continuing_end)
        ct = continuing_total(receipts, cal.continuing_start, cal.continuing_end)
        c = s.get(Committee, org_id)
        combined = build_combined(
            org_id=org_id,
            pp_beginning_cents=sm.beginning_cents if sm else None,
            pp_raised_excl_loans_cents=sm.raised_excl_loans_cents if sm else None,
            pp_loans_cents=sm.loans_cents if sm else None,
            pp_expended_cents=sm.expended_cents if sm else None,
            continuing=ct, has_pre_primary=sm is not None,
        )
        out = combined.to_dict()
        out["candidate"] = c.candidate_name if c else None
        out["district"] = c.district if c else None
        out["as_of"] = as_of(s, year)
        out["window"] = {"from": cal.continuing_start.isoformat(),
                         "to": cal.continuing_end.isoformat()}
        return out


def district_combined(district: str, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        org_ids = [c.org_id for c in s.scalars(
            select(Committee).where(Committee.district == district))]
    return {"district": district,
            "candidates": [get_combined(o, year) for o in org_ids]}


# ---- Axis B: flags ------------------------------------------------------
def get_flags(district=None, org_id=None, year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        run = _latest_run(s, year)
        q = select(Flag)
        if run:
            q = q.where(Flag.run_id == run.run_id)
        if org_id:
            q = q.where(Flag.org_id == org_id)
        if district:
            org_ids = [c.org_id for c in s.scalars(
                select(Committee).where(Committee.district == district))]
            q = q.where(Flag.org_id.in_(org_ids))
        flags = [{"org_id": f.org_id, "candidate": f.candidate, "type": f.type,
                  "severity": f.severity, "detail": f.detail} for f in s.scalars(q)]
        return {"as_of": as_of(s, year), "count": len(flags), "flags": flags}


# ---- calendar / status --------------------------------------------------
def get_calendar(year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        return active_calendar(s, year).to_dict()


def refresh_status(year=None) -> dict:
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        run = _latest_run(s, year)
        info = {"year": year, **as_of(s, year)}
        if run:
            info["extract_as_of"] = {
                "max_filed_date": run.max_filed_date.isoformat() if run.max_filed_date else None,
                "max_receipt_date": run.max_receipt_date.isoformat() if run.max_receipt_date else None,
            }
            info["note"] = run.note
        return info


# ---- flexible category query (Axis A × Axis B) --------------------------
def _resolve_org_ids(session, select_obj: dict, year: int) -> list[str]:
    if select_obj.get("committee"):
        return [select_obj["committee"]]
    q = select(Committee).where(Committee.cycle_year == year)
    if select_obj.get("district"):
        q = q.where(Committee.district == select_obj["district"])
    if select_obj.get("candidate"):
        from sqlalchemy import func
        q = q.where(func.lower(Committee.candidate_name).like(f"%{select_obj['candidate'].lower()}%"))
    if select_obj.get("party"):
        q = q.where(Committee.party == select_obj["party"])
    if select_obj.get("office"):
        q = q.where(Committee.office.ilike(f"%{select_obj['office']}%"))
    return [c.org_id for c in session.scalars(q.limit(200))]


def query(select_obj: dict, category: str, window: dict | None = None,
          options: dict | None = None, year=None) -> dict:
    """The explicit 'select between categories' surface (Axis A × Axis B)."""
    year = year or get_settings().default_cycle_year
    window = window or {}
    options = options or {}
    with session_scope() as s:
        org_ids = _resolve_org_ids(s, select_obj, year)

    cat = category.lower()
    data: object
    if cat in ("filing_history", "filings"):
        data = [list_filings(o) for o in org_ids]
    elif cat == "report" and org_ids:
        fls = list_filings(org_ids[0])["filings"]
        data = get_report(fls[0]["filing_id"]) if fls else None
    elif cat == "summary":
        data = [get_summary(o) for o in org_ids]
    elif cat in ("continuing_total", "continuing"):
        data = [get_continuing(o, window.get("from"), window.get("to"), year) for o in org_ids]
    elif cat == "combined":
        data = [get_combined(o, year) for o in org_ids]
    elif cat == "contributions":
        data = [get_contributions(org_id=o, date_from=window.get("from"),
                                  date_to=window.get("to"),
                                  min_amount=options.get("min_amount"),
                                  dedup=options.get("dedup", True), year=year) for o in org_ids]
    elif cat == "loans":
        data = [get_contributions(org_id=o, receipt_type="Loan",
                                  date_from=window.get("from"), date_to=window.get("to"),
                                  year=year) for o in org_ids]
    elif cat == "flags":
        data = get_flags(org_id=org_ids[0] if len(org_ids) == 1 else None,
                         district=select_obj.get("district"), year=year)
    else:
        raise NotFound(f"unknown category {category}")

    with session_scope() as s:
        caveats = ["Ending omits continuing-period spending"] if cat == "combined" else []
        return {"as_of": as_of(s, year), "selection": select_obj, "category": cat,
                "resolved_org_ids": org_ids, "data": data, "caveats": caveats}


# ---- dashboard overview (web) ------------------------------------------
def dashboard_overview(year=None) -> dict:
    """Roster-wide combined figures + inline flags for the web dashboard — one
    session, roster-driven (mirrors the xlsx deliverable). Money stays in cents;
    the web layer formats it."""
    from .roster import all_roster_candidates, norm_name, resolve_org_id

    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        cal = active_calendar(s, year)
        name_index: dict[str, list[str]] = {}
        for c in s.scalars(select(Committee)):
            if c.candidate_name:
                name_index.setdefault(norm_name(c.candidate_name), []).append(c.org_id)

        rows, tot_raised, tot_loans, tot_ending, flagged, with_cmte = [], 0, 0, 0, 0, 0
        for district, name in all_roster_candidates():
            res = resolve_org_id(name, name_index)
            org_id = res["org_id"]
            flags: list[dict] = []
            if org_id:
                with_cmte += 1
                rep, sm = _summary_for_org(s, org_id)
                receipts = query_window_receipts(s, org_id, year, cal.continuing_start, cal.continuing_end)
                ct = continuing_total(receipts, cal.continuing_start, cal.continuing_end)
                combined = build_combined(
                    org_id,
                    sm.beginning_cents if sm else None,
                    sm.raised_excl_loans_cents if sm else None,
                    sm.loans_cents if sm else None,
                    sm.expended_cents if sm else None,
                    ct, has_pre_primary=sm is not None,
                )
                comm = s.get(Committee, org_id)
                if combined.loans_cents > 0 and combined.loans_cents >= combined.raised_cents:
                    flags.append({"type": "large_loan", "severity": "high"})
                elif combined.loans_cents >= 1_000_000:
                    flags.append({"type": "large_loan", "severity": "warn"})
                if not combined.has_pre_primary:
                    flags.append({"type": "no_pre_primary", "severity": "info"})
                row = {
                    "district": district, "candidate": name, "org_id": org_id,
                    "party": comm.party if comm else None,
                    "beginning_cents": combined.beginning_cents,
                    "raised_cents": combined.raised_cents,
                    "loans_cents": combined.loans_cents,
                    "expended_cents": combined.expended_cents,
                    "ending_cents": combined.ending_cents,
                    "continuing_raised_cents": combined.continuing_raised_cents,
                    "has_pre_primary": combined.has_pre_primary,
                    "note": combined.note, "flags": flags,
                    "identity_ok": combined.identity_ok(),
                }
                tot_raised += combined.raised_cents
                tot_loans += combined.loans_cents
                tot_ending += combined.ending_cents
            else:
                if res["source"] == "no_committee":
                    flags.append({"type": "no_committee", "severity": "warn"})
                elif res["multiple"]:
                    flags.append({"type": "multiple_committees", "severity": "warn"})
                row = {
                    "district": district, "candidate": name, "org_id": None, "party": None,
                    "beginning_cents": 0, "raised_cents": 0, "loans_cents": 0,
                    "expended_cents": 0, "ending_cents": 0, "continuing_raised_cents": 0,
                    "has_pre_primary": False,
                    "note": ("No committee found" if res["source"] == "no_committee" else "Unresolved"),
                    "flags": flags, "identity_ok": True,
                }
            if flags:
                flagged += 1
            rows.append(row)

        return {
            "as_of": as_of(s, year),
            "calendar": cal.to_dict(),
            "totals": {
                "raised_cents": tot_raised, "loans_cents": tot_loans,
                "ending_cents": tot_ending, "candidates": len(rows),
                "with_committee": with_cmte, "flagged": flagged,
                "districts": len({r["district"] for r in rows}),
            },
            "rows": rows,
        }


def candidate_dossier(org_id: str, year=None) -> dict:
    """Everything the detail page needs, composed from the atomic service calls."""
    year = year or get_settings().default_cycle_year
    with session_scope() as s:
        cal = active_calendar(s, year)
    return {
        "committee": get_committee(org_id),
        "combined": get_combined(org_id, year),
        "summary": get_summary(org_id),
        "continuing": get_continuing(org_id, year=year),
        "contributions": get_contributions(
            org_id=org_id, date_from=cal.continuing_start.isoformat(),
            date_to=cal.continuing_end.isoformat(), year=year),
        "filings": list_filings(org_id),
        "flags": get_flags(org_id=org_id, year=year),
    }

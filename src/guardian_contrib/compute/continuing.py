"""Continuing total — Appendix C / Section 7. Count each contribution ONCE.

Continuing reports are incremental (Rule 2); the correct total is the union of
continuing-window receipts from the bulk extract, deduped by Receipt ID, with
Refund / Loan-Forgiveness types excluded and Amended='Y' rows dropped, split into
Loans vs Raised (everything else).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest.bulk import NON_RECEIPT_TYPES
from ..models import Receipt


@dataclass
class ContinuingTotal:
    raised_cents: int = 0
    loans_cents: int = 0
    count: int = 0
    receipt_ids: set[str] = field(default_factory=set)
    duplicates: int = 0  # how many duplicate Receipt IDs were collapsed (should be 0)


def continuing_total(receipts, start: dt.date, end: dt.date) -> ContinuingTotal:
    """Core logic over any iterable of receipt-like objects (attrs: receipt_id,
    date, amount_cents, receipt_type, amended)."""
    out = ContinuingTotal()
    for r in receipts:
        if (r.amended or "").upper() == "Y":
            continue
        if r.receipt_type in NON_RECEIPT_TYPES:
            continue
        if r.date is None or r.date < start or r.date > end:
            continue
        if r.receipt_id in out.receipt_ids:  # dedup (Rule 2)
            out.duplicates += 1
            continue
        out.receipt_ids.add(r.receipt_id)
        if r.receipt_type == "Loan":
            out.loans_cents += r.amount_cents
        else:
            out.raised_cents += r.amount_cents
    out.count = len(out.receipt_ids)
    return out


def query_window_receipts(
    session: Session, org_id: str, cycle_year: int,
    start: dt.date | None = None, end: dt.date | None = None,
) -> list[Receipt]:
    q = select(Receipt).where(Receipt.org_id == org_id, Receipt.cycle_year == cycle_year)
    if start is not None:
        q = q.where(Receipt.date >= start)
    if end is not None:
        q = q.where(Receipt.date <= end)
    return list(session.scalars(q))


def continuing_for_org(
    session: Session, org_id: str, cycle_year: int, start: dt.date, end: dt.date
) -> ContinuingTotal:
    return continuing_total(
        query_window_receipts(session, org_id, cycle_year, start, end), start, end
    )

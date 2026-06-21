"""Computed flags / alerts (Rules 8, 9; project brief self-dealing note).

A flag is a plain dict: {org_id, candidate, type, severity, detail}. The runner
persists them; the API/MCP serve them. Severity: info | warn | high.
"""
from __future__ import annotations

import datetime as dt

from ..money import decimal_str

# Absolute self-loan threshold (e.g. Derek Porter's $40k self-loan). Configurable.
LARGE_LOAN_ABS_CENTS = 1_000_000  # $10,000
SUB_THRESHOLD_CENTS = 100_000     # $1,000 — OK continuing-report itemization floor
NON_FLAG_RECEIPT_TYPES = {"Refund", "Loan Forgiveness",
                          "Loan Balance Decrease due to Loan Forgiveness", "Loan"}


def _flag(org_id, candidate, type_, severity, detail) -> dict:
    return {"org_id": org_id, "candidate": candidate, "type": type_,
            "severity": severity, "detail": detail}


def large_loan(org_id, candidate, raised_cents: int, loans_cents: int,
               abs_threshold: int = LARGE_LOAN_ABS_CENTS) -> dict | None:
    if loans_cents <= 0:
        return None
    if loans_cents >= raised_cents:
        return _flag(org_id, candidate, "large_loan", "high",
                     f"Loan ${decimal_str(loans_cents)} ≥ raised ${decimal_str(raised_cents)} "
                     f"(possible self-dealing)")
    if loans_cents >= abs_threshold:
        return _flag(org_id, candidate, "large_loan", "warn",
                     f"Loan ${decimal_str(loans_cents)} exceeds "
                     f"${decimal_str(abs_threshold)} threshold")
    return None


def sub_threshold(org_id, candidate, receipts, start: dt.date, end: dt.date) -> list[dict]:
    """Continuing-window receipts < $1,000 with no continuing report (Rule 9)."""
    out = []
    for r in receipts:
        if (r.amended or "").upper() == "Y" or r.receipt_type in NON_FLAG_RECEIPT_TYPES:
            continue
        if r.date is None or r.date < start or r.date > end:
            continue
        if 0 < r.amount_cents < SUB_THRESHOLD_CENTS:
            out.append(_flag(
                org_id, candidate, "sub_threshold", "info",
                f"${decimal_str(r.amount_cents)} on {r.date} (< $1,000; not on any "
                f"continuing report — decide whether to count)"))
    return out


def amended_report_used(org_id, candidate, version_count: int) -> dict | None:
    if version_count and version_count > 1:
        return _flag(org_id, candidate, "amended_report_used", "warn",
                     f"Latest of {version_count} versions used (amendment exists)")
    return None


def multiple_committees(org_id, candidate, other_org_ids: list[str]) -> dict | None:
    if other_org_ids:
        return _flag(org_id, candidate, "multiple_committees", "warn",
                     f"Candidate has other committees: {', '.join(other_org_ids)} "
                     f"(used regular-cycle {org_id})")
    return None


def no_pre_primary(org_id, candidate) -> dict:
    return _flag(org_id, candidate, "no_pre_primary", "warn",
                 "Committee found but no Pre-Primary report filed")


def no_committee_found(candidate) -> dict:
    return _flag(None, candidate, "no_committee_found", "warn",
                 "No committee found on Guardian for roster candidate")


def identity_mismatch(org_id, candidate, detail: str) -> dict:
    return _flag(org_id, candidate, "identity_mismatch", "high", detail)

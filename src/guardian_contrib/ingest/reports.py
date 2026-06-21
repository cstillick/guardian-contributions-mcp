"""Report PDF parsing — the Schedule Summary (Section 6).

Extraction reads the **Reporting-Period column (left), not Aggregate** (Rule 6):
in the pypdf text layer the reporting-period value is the FIRST money token after
each line label (verified against ground truth — Roe 2026: Beginning $29,863.66,
Raised $9,250, Expended $4,278.24, all matching the combined sheet to the penny).

The parser also reads the report's own period/year so the ingester can reject a
wrong-cycle PDF (Rule 7 — a saved 'HD42 Cindy Roe 2026' file was really her 2024
report).
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass

from pypdf import PdfReader

from ..money import to_cents

_MONEY = r"(\(?\$?-?[\d,]+\.\d{2}\)?)"


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _first_money_after(text: str, label: str) -> int | None:
    # First money token after the label; .*? (DOTALL) skips intervening non-money
    # text like the "[Line 1 + Line 8 - Line 16]" annotation before ENDING BALANCE.
    m = re.search(label + r".*?" + _MONEY, text, re.S)
    return to_cents(m.group(1)) if m else None


@dataclass
class ScheduleSummary:
    beginning_cents: int | None
    total_received_cents: int | None
    loans_cents: int | None
    expended_cents: int | None
    ending_cents: int | None
    period_start: dt.date | None
    period_end: dt.date | None
    district: str | None
    office: str | None
    amended: bool
    report_year: int | None

    @property
    def raised_excl_loans_cents(self) -> int | None:
        if self.total_received_cents is None or self.loans_cents is None:
            return None
        return self.total_received_cents - self.loans_cents

    def identity_ok(self) -> bool | None:
        """Beginning + Received − Expended == Ending (Rule §6 sanity / §10.4)."""
        vals = (self.beginning_cents, self.total_received_cents,
                self.expended_cents, self.ending_cents)
        if any(v is None for v in vals):
            return None
        return (self.beginning_cents + self.total_received_cents
                - self.expended_cents) == self.ending_cents


_OFFICE_RE = re.compile(r"(REPRESENTATIVE|SENATE|SENATOR|GOVERNOR|STATE\s+\w+)", re.I)
_DISTRICT_RE = re.compile(r"DISTRICT\s*(\d+)", re.I)
_PERIOD_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2})/(\d{2})/(\d{4})")


def parse_schedule_summary(text: str) -> ScheduleSummary:
    beginning = _first_money_after(text, r"BEGINNING BALANCE:")
    received = _first_money_after(text, r"TOTAL FUNDS RECEIVED:")
    loans = _first_money_after(text, r"7a\.\s*Loans \[Schedule C\]")
    expended = _first_money_after(text, r"TOTAL FUNDS EXPENDED:")
    ending = _first_money_after(text, r"ENDING BALANCE:")

    period_start = period_end = None
    pm = _PERIOD_RE.search(text)
    if pm:
        period_start = dt.date(int(pm.group(3)), int(pm.group(1)), int(pm.group(2)))
        period_end = dt.date(int(pm.group(6)), int(pm.group(4)), int(pm.group(5)))

    office = None
    om = _OFFICE_RE.search(text)
    if om:
        office = om.group(1).title()
    dm = _DISTRICT_RE.search(text)
    district = dm.group(1) if dm else None

    am = re.search(r"AMENDED:\s*(YES|NO)", text, re.I)
    amended = bool(am) and am.group(1).upper() == "YES"

    # Report year: prefer the period's year; fall back to a '<YYYY> ... REPORT' header.
    report_year = period_end.year if period_end else None
    if report_year is None:
        ym = re.search(r"(\d{4})\s+[A-Z0-9 \-]*REPORT", text)
        report_year = int(ym.group(1)) if ym else None

    return ScheduleSummary(
        beginning_cents=beginning,
        total_received_cents=received,
        loans_cents=loans,
        expended_cents=expended,
        ending_cents=ending,
        period_start=period_start,
        period_end=period_end,
        district=district,
        office=office,
        amended=amended,
        report_year=report_year,
    )


def classify_report(label: str) -> str | None:
    """Section 8: 'periodic' (has a Schedule Summary) vs 'itemized' (Continuing-style)."""
    u = (label or "").upper()
    if "CONTINUING" in u:
        return "itemized"
    if "REGISTRATION" in u or "AFFIDAVIT" in u:
        return None
    if "REPORT" in u:
        return "periodic"
    return None

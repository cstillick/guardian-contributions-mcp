"""Bulk contribution/loan extract: download, parse, normalize.

Hard Rule note: do NOT use a naive RFC4180 parser — stray unescaped quotes cause
field-misalignment cascades and silent undercounts. We use the Appendix-A
record-split parser (split records on \\r?\\n(?="), strip outer quotes, split on
'","') and validate the 23-field width per record.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..money import to_cents

EXPECTED_COLUMNS = [
    "Receipt ID", "Org ID", "Receipt Type", "Receipt Date", "Receipt Amount",
    "Description", "Receipt Source Type", "Last Name", "First Name", "Middle Name",
    "Suffix", "Address 1", "Address 2", "City", "State", "Zip", "Filed Date",
    "Committee Type", "Committee Name", "Candidate Name", "Amended", "Employer",
    "Occupation",
]
# Excluded receipt types when summing real money (Rule: continuing total).
NON_RECEIPT_TYPES = {
    "Refund",
    "Loan Forgiveness",
    "Loan Balance Decrease due to Loan Forgiveness",
}


@dataclass
class ReceiptRecord:
    cycle_year: int
    receipt_id: str
    org_id: str
    date: dt.date | None
    amount_cents: int
    receipt_type: str
    source_type: str
    source_name: str
    city: str
    state: str
    zip: str
    filed_date: dt.date | None
    amended: str
    committee_name: str
    candidate_name: str
    committee_type: str
    description: str


def _to_date(v: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", v or "")
    return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def download_bulk(settings: Settings, year: int | None = None) -> bytes:
    url = settings.bulk_url(year)
    with httpx.Client(
        timeout=settings.request_timeout,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    ) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def unzip_to_text(raw: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(raw))
    return z.read(z.namelist()[0]).decode("utf-8", errors="replace")


def parse_extract(text: str) -> tuple[list[str], dict[str, int], list[list[str]], int]:
    """Appendix A record-split parser. Returns (header, idx, rows, malformed_dropped)."""
    recs = re.split(r"\r?\n(?=\")", text)

    def fields(rec: str) -> list[str]:
        s = rec.rstrip("\r")
        if s.startswith('"'):
            s = s[1:]
        if s.endswith('"'):
            s = s[:-1]
        return s.split('","')

    header = fields(recs[0])
    idx = {h.strip(): i for i, h in enumerate(header)}
    rows: list[list[str]] = []
    bad = 0
    for rec in recs[1:]:
        if not rec.strip():
            continue
        f = fields(rec)
        if len(f) == len(header):
            rows.append(f)
        else:
            bad += 1
    return header, idx, rows, bad


def _source_name(g) -> str:
    parts = [g("First Name"), g("Middle Name"), g("Last Name"), g("Suffix")]
    name = " ".join(p for p in parts if p).strip()
    return name or g("Committee Name") or ""


def iter_receipts(rows, idx, cycle_year: int):
    """Yield normalized ReceiptRecords. Drops blank-Org-ID rows (Rule 14)."""
    def col(r, name):
        i = idx.get(name)
        return (r[i].strip() if i is not None and i < len(r) else "")

    for r in rows:
        org = col(r, "Org ID")
        if not org:  # Rule 14: blank Org ID dropped before dedup/sum
            continue
        g = lambda name: col(r, name)  # noqa: E731
        yield ReceiptRecord(
            cycle_year=cycle_year,
            receipt_id=g("Receipt ID"),
            org_id=org,
            date=_to_date(g("Receipt Date")),
            amount_cents=to_cents(g("Receipt Amount")) or 0,
            receipt_type=g("Receipt Type"),
            source_type=g("Receipt Source Type"),
            source_name=_source_name(g),
            city=g("City"),
            state=g("State"),
            zip=g("Zip"),
            filed_date=_to_date(g("Filed Date")),
            amended=g("Amended"),
            committee_name=g("Committee Name"),
            candidate_name=g("Candidate Name"),
            committee_type=g("Committee Type"),
            description=g("Description"),
        )


def freshness(rows, idx) -> tuple[dt.date | None, dt.date | None]:
    """Max Filed Date and max Receipt Date in the extract (Rule 13)."""
    fi, ri = idx.get("Filed Date"), idx.get("Receipt Date")
    fd = [d for d in (_to_date(r[fi]) for r in rows if fi is not None and fi < len(r)) if d]
    rd = [d for d in (_to_date(r[ri]) for r in rows if ri is not None and ri < len(r)) if d]
    return (max(fd) if fd else None, max(rd) if rd else None)

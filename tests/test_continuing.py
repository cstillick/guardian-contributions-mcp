"""Continuing total (Appendix C / §7): dedup, exclusions, loan/raised split, and
the headline reproduction — Roe's continuing window sums to exactly $33,500."""
import datetime as dt
from collections import namedtuple

from conftest import FIXTURES

from guardian_contrib.compute.continuing import continuing_for_org, continuing_total
from guardian_contrib.db import session_scope
from guardian_contrib.ingest.runner import run_bulk_ingest

R = namedtuple("R", "receipt_id date amount_cents receipt_type amended")
START, END = dt.date(2026, 6, 2), dt.date(2026, 6, 16)

# Roe's actual 12 continuing-window receipts (from the live extract).
ROE = [
    R("2539440", dt.date(2026, 6, 4), 150000, "Monetary", ""),
    R("2539441", dt.date(2026, 6, 4), 250000, "Monetary", ""),
    R("2539442", dt.date(2026, 6, 4), 300000, "Monetary", ""),
    R("2539445", dt.date(2026, 6, 4), 500000, "Monetary", ""),
    R("2539447", dt.date(2026, 6, 4), 500000, "Monetary", ""),
    R("2539449", dt.date(2026, 6, 4), 350000, "Monetary", ""),
    R("2539450", dt.date(2026, 6, 4), 150000, "Monetary", ""),
    R("2539452", dt.date(2026, 6, 4), 150000, "Monetary", ""),
    R("2539454", dt.date(2026, 6, 4), 150000, "Monetary", ""),
    R("2539463", dt.date(2026, 6, 4), 200000, "Monetary", ""),
    R("2552624", dt.date(2026, 6, 11), 350000, "Monetary", ""),
    R("2553226", dt.date(2026, 6, 13), 300000, "Monetary", ""),
]


def test_roe_continuing_is_33500():
    ct = continuing_total(ROE, START, END)
    assert ct.raised_cents == 3_350_000
    assert ct.loans_cents == 0
    assert ct.count == 12
    assert ct.duplicates == 0


def test_dedup_excludes_and_splits():
    rows = ROE + [
        R("2539440", dt.date(2026, 6, 4), 150000, "Monetary", ""),   # duplicate id
        R("9000001", dt.date(2026, 6, 5), 1_000_00, "Loan", ""),     # -> loans
        R("9000002", dt.date(2026, 6, 5), 5000, "Refund", ""),       # excluded type
        R("9000003", dt.date(2026, 6, 5), 5000, "Monetary", "Y"),    # amended -> excluded
        R("9000004", dt.date(2026, 6, 1), 5000, "Monetary", ""),     # before window
        R("9000005", dt.date(2026, 6, 17), 5000, "Monetary", ""),    # after window
    ]
    ct = continuing_total(rows, START, END)
    assert ct.raised_cents == 3_350_000     # unchanged by all the noise
    assert ct.loans_cents == 100_000
    assert ct.duplicates == 1


def test_continuing_from_store(temp_db):
    text = (FIXTURES / "bulk_slice_2026.csv").read_text()
    with session_scope() as s:
        stats = run_bulk_ingest(s, text, 2026)
    assert stats.receipts == 303
    with session_scope() as s:
        ct = continuing_for_org(s, "11932", 2026, START, END)
    assert ct.raised_cents == 3_350_000
    assert ct.count == 12

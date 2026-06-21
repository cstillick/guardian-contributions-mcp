"""Parser correctness against a real, correct (live-fetched) 2026 Pre-Primary PDF.
Reads the Reporting-Period column (Rule 6); values verified against the combined
sheet to the penny."""
from conftest import FIXTURES

from guardian_contrib.ingest.reports import parse_schedule_summary, pdf_text

ROE = FIXTURES / "roe_2026_pre_primary.pdf"


def test_roe_schedule_summary_exact():
    s = parse_schedule_summary(pdf_text(ROE.read_bytes()))
    assert s.beginning_cents == 2986366
    assert s.total_received_cents == 925000
    assert s.loans_cents == 0
    assert s.expended_cents == 427824
    assert s.ending_cents == 3483542
    assert s.raised_excl_loans_cents == 925000
    assert s.report_year == 2026
    assert s.district == "42"
    assert s.identity_ok() is True


def test_pre_primary_raised_plus_continuing_equals_combined():
    """PP raised ($9,250) + continuing ($33,500) = combined raised ($42,750)."""
    s = parse_schedule_summary(pdf_text(ROE.read_bytes()))
    assert s.raised_excl_loans_cents + 3_350_000 == 4_275_000

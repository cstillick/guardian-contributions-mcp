import datetime as dt
import pathlib

import pytest

import guardian_contrib.config as cfg
from guardian_contrib import db

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Isolated SQLite file DB per test."""
    dbfile = tmp_path / "test.db"
    monkeypatch.setenv("GUARDIAN_DATABASE_URL", f"sqlite:///{dbfile}")
    cfg._settings = None
    db.reset_engine()
    db.init_db()
    yield
    db.reset_engine()
    cfg._settings = None


def seed_roe_store(year: int = 2026) -> None:
    """Seed the active DB with the bulk slice + Roe's real Pre-Primary summary + a Run,
    so combined/summary/continuing reproduce the known-good Roe figures offline."""
    from guardian_contrib.db import session_scope
    from guardian_contrib.ingest.reports import parse_schedule_summary, pdf_text
    from guardian_contrib.ingest.runner import run_bulk_ingest
    from guardian_contrib.models import Committee, Report, Run, Summary

    text = (FIXTURES / "bulk_slice_2026.csv").read_text()
    sm = parse_schedule_summary(pdf_text((FIXTURES / "roe_2026_pre_primary.pdf").read_bytes()))
    with session_scope() as s:
        run_bulk_ingest(s, text, year)
        roe = s.get(Committee, "11932")
        roe.district, roe.office, roe.candidate_name = "HD-42", "STATE REPRESENTATIVE", "ROE, CYNTHIA JO"
        s.add(Report(filing_id="233662", org_id="11932", cycle_year=year,
                     report_type="2026 PRE-PRIMARY REPORT", report_class="periodic",
                     period_start=sm.period_start, period_end=sm.period_end,
                     amended=False, is_latest_version=True))
        s.flush()
        s.add(Summary(filing_id="233662", beginning_cents=sm.beginning_cents,
                      total_received_cents=sm.total_received_cents, loans_cents=sm.loans_cents,
                      expended_cents=sm.expended_cents, ending_cents=sm.ending_cents))
        s.add(Run(started_at=dt.datetime(2026, 6, 17), cycle_year=year,
                  max_filed_date=dt.date(2026, 6, 19), max_receipt_date=dt.date(2026, 6, 15),
                  primary_date=dt.date(2026, 6, 16), pre_primary_start=dt.date(2026, 4, 1),
                  pre_primary_end=dt.date(2026, 6, 1), continuing_start=dt.date(2026, 6, 2),
                  continuing_end=dt.date(2026, 6, 16), extract_rows=303, changed_since_prev=True))

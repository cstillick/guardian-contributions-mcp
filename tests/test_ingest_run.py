"""Regression: the full ingest_run orchestration (bulk + enrich + flags + run log)
works offline with an injected client. Guards the bug where _enrich_and_flag read
candidate_name off Receipt rows (it lives on Committee)."""
from conftest import FIXTURES

from guardian_contrib.db import session_scope
from guardian_contrib.ingest.guardian_client import CommitteeDetail
from guardian_contrib.ingest.runner import ingest_run
from guardian_contrib.models import Committee


class _FakeClient:
    """Stub Guardian client — no network. Returns committee detail, no PP report."""
    def committee_detail(self, org_id, html=None):
        return CommitteeDetail(
            org_id=org_id, legal_name="TEST CMTE", office="STATE REPRESENTATIVE",
            district="HD-42", district_raw="DISTRICT 42", party="(R)",
            election="2026 NOVEMBER GENERAL ELECTION", election_cycle="2026 CYCLE",
            status="Active", is_regular_cycle=True, cycle_year=2026)

    def list_filings(self, org_id, html=None):
        return []

    def fetch_report(self, org_id, want=r"PRE-PRIMARY"):
        return None

    def close(self):
        pass


def test_ingest_run_enrich_path_offline(temp_db):
    text = (FIXTURES / "bulk_slice_2026.csv").read_text()
    result = ingest_run(year=2026, enrich_roster=True, client=_FakeClient(), bulk_text=text)

    assert result["run_id"] >= 1
    assert result["stats"]["receipts"] == 303
    assert result["enriched"] >= 1          # roster names resolved + enriched, no crash
    with session_scope() as s:
        roe = s.get(Committee, "11932")     # in the slice, resolves via override
        assert roe is not None and roe.district == "HD-42"  # detail enrichment applied

"""Opt-in live end-to-end against guardian.ok.gov (set GUARDIAN_LIVE=1).

Downloads the real bulk extract, fetches Roe's Pre-Primary via the postback chain,
and reconciles the combined figure to the known-good sheet — to the penny. This is
the full-pipeline acceptance check; skipped by default so the suite stays offline."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("GUARDIAN_LIVE") != "1",
    reason="set GUARDIAN_LIVE=1 to run live Guardian tests",
)


def test_live_roe_combined_to_the_penny(temp_db):
    from guardian_contrib import service
    from guardian_contrib.config import get_settings
    from guardian_contrib.db import session_scope
    from guardian_contrib.ingest import bulk
    from guardian_contrib.ingest.guardian_client import GuardianClient
    from guardian_contrib.ingest.runner import enrich_committee, run_bulk_ingest

    settings = get_settings()
    text = bulk.unzip_to_text(bulk.download_bulk(settings, 2026))
    with session_scope() as s:
        stats = run_bulk_ingest(s, text, 2026)
    assert stats.receipts > 50_000  # the whole state

    with GuardianClient(settings) as client, session_scope() as s:
        info = enrich_committee(s, client, "11932", 2026)
    assert info["report_stored"] and info["rejected"] is None

    out = service.get_combined("11932", 2026)
    assert out["beginning"] == "29863.66"
    assert out["raised"] == "42750.00"
    assert out["expended"] == "4278.24"
    assert out["ending"] == "68335.42"
    assert out["continuing_raised"] == "33500.00"
    assert out["identity_ok"] is True

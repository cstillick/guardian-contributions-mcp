"""The xlsx builder renders the Roe row with penny-accurate components and a LIVE
End-Balance formula, plus the status banner."""
from conftest import seed_roe_store

from guardian_contrib.builder.xlsx import build_workbook


def _find_row(ws, candidate):
    for row in ws.iter_rows(min_row=3):
        if row[1].value == candidate:
            return row
    return None


def test_roe_row_values_and_formula(temp_db):
    seed_roe_store()
    ws = build_workbook(2026).active
    row = _find_row(ws, "Cindy Roe")
    assert row is not None, "Roe row missing"
    assert row[0].value == "HD-42"
    assert abs(row[2].value - 29863.66) < 1e-6      # Beginning
    assert abs(row[3].value - 42750.00) < 1e-6      # Raised (PP + continuing)
    assert abs(row[5].value - 4278.24) < 1e-6       # Expended
    assert row[6].value == f"=C{row[6].row}+D{row[6].row}+E{row[6].row}-F{row[6].row}"
    assert "33500" in (row[7].value or "")          # continuing note
    assert row[2].number_format.startswith("_($*")  # accounting format


def test_banner_and_no_committee_rows(temp_db):
    seed_roe_store()
    ws = build_workbook(2026).active
    assert "Ending omits continuing-period spending" in ws.cell(row=1, column=1).value
    # Grant Worley is on the no-committee list -> a row with that note, zeros.
    row = _find_row(ws, "Grant Worley")
    assert row is not None and "No committee" in (row[7].value or "")


def test_write_deliverable_archives_prior(temp_db, tmp_path):
    seed_roe_store()
    from guardian_contrib.builder.xlsx import write_deliverable

    p1 = write_deliverable(2026, out_dir=tmp_path)
    assert p1.exists()
    p2 = write_deliverable(2026, out_dir=tmp_path)  # same-day rerun
    assert p2.exists()
    archived = list(tmp_path.glob("*_ARCHIVED_*.xlsx"))
    assert len(archived) >= 1, "prior deliverable must be archived, never overwritten (Rule 11)"

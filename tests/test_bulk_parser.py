"""Appendix-A record-split parser: 23-field validation, embedded commas survive,
blank-Org-ID rows dropped (Rule 14), malformed records dropped not misaligned."""
from conftest import FIXTURES

from guardian_contrib.ingest import bulk

HEADER = '","'.join(bulk.EXPECTED_COLUMNS)


def _rec(*fields):
    return '"' + '","'.join(fields) + '"'


def test_embedded_comma_does_not_split_fields():
    # City "LINDSAY, OK" style — comma inside a quoted field must not split.
    header = '"' + HEADER + '"'
    row = _rec("100", "11932", "Monetary", "06/04/2026", "1500", "", "Individual",
               "Doe", "Jane", "", "", "123 A St", "", "OKLAHOMA CITY, OK", "OK",
               "73101", "06/05/2026", "Candidate Committee", "ROE CMTE", "ROE, CYNTHIA",
               "N", "ACME, INC", "ENGINEER")
    header_f, idx, rows, bad = bulk.parse_extract(header + "\n" + row)
    assert len(header_f) == 23 and bad == 0 and len(rows) == 1
    assert rows[0][idx["City"]] == "OKLAHOMA CITY, OK"
    assert rows[0][idx["Candidate Name"]] == "ROE, CYNTHIA"


def test_malformed_record_dropped_not_misaligned():
    header = '"' + HEADER + '"'
    good = _rec(*(["x"] * 23))
    short = _rec(*(["y"] * 20))   # wrong width -> dropped
    _, _, rows, bad = bulk.parse_extract("\n".join([header, good, short]))
    assert len(rows) == 1 and bad == 1


def test_blank_org_id_rows_dropped(tmp_path):
    header = '"' + HEADER + '"'
    blank_org = _rec("", "", "Monetary", "06/04/2026", "25", "", "PAC", "", "", "",
                     "", "", "", "", "", "", "06/05/2026", "", "TARGA PAC", "", "N", "", "")
    real = _rec("101", "11932", "Monetary", "06/04/2026", "1500", "", "Individual", "Doe",
                "J", "", "", "", "", "", "OK", "", "06/05/2026", "Candidate Committee",
                "ROE", "ROE, C", "N", "", "")
    header_f, idx, rows, bad = bulk.parse_extract("\n".join([header, blank_org, real]))
    recs = list(bulk.iter_receipts(rows, idx, 2026))
    assert len(recs) == 1 and recs[0].org_id == "11932"   # blank-Org-ID dropped


def test_real_slice_parses_clean():
    text = (FIXTURES / "bulk_slice_2026.csv").read_text()
    header, idx, rows, bad = bulk.parse_extract(text)
    assert len(header) == 23 and bad == 0 and len(rows) == 303

"""Lock the core invariant against the known-good deliverable: every row of the
combined sheet satisfies Beginning + Raised + Loans − Expended = Ending
(workflow §10.4 / §10.11). Zero mismatches allowed."""
import csv
import re

from conftest import FIXTURES

from guardian_contrib.money import to_cents

CSV = FIXTURES / "combined_known_good_2026-06-15.csv"
_DIST = re.compile(r"^[HS]D-\d+$")


def _data_rows():
    with open(CSV, newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 7 and _DIST.match(row[0].strip()):
                yield row


def test_every_row_satisfies_balance_identity():
    rows = list(_data_rows())
    assert len(rows) >= 70, "fixture should hold the statewide House roster"
    mismatches = []
    for r in rows:
        beg = to_cents(r[2]) or 0
        raised = to_cents(r[3]) or 0
        loan = to_cents(r[4]) or 0
        exp = to_cents(r[5]) or 0
        end = to_cents(r[6]) or 0
        if beg + raised + loan - exp != end:
            mismatches.append((r[0], r[1], beg, raised, loan, exp, end))
    assert mismatches == [], f"{len(mismatches)} identity mismatches: {mismatches[:5]}"


def test_roe_row_matches_ground_truth():
    roe = next(r for r in _data_rows() if "roe" in r[1].lower())
    assert (to_cents(roe[2]), to_cents(roe[3]), to_cents(roe[4]),
            to_cents(roe[5]), to_cents(roe[6])) == (2986366, 4275000, None, 427824, 6833542)

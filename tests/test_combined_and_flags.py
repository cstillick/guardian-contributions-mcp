"""Combined layering (§9) reproduces the Roe combined row from its pieces, and the
flag rules fire correctly."""
import datetime as dt
from collections import namedtuple

from guardian_contrib.compute import flags
from guardian_contrib.compute.combined import build_combined
from guardian_contrib.compute.continuing import ContinuingTotal

R = namedtuple("R", "receipt_id date amount_cents receipt_type amended")


def test_combined_reproduces_roe_row():
    cont = ContinuingTotal(raised_cents=3_350_000, loans_cents=0, count=12)
    c = build_combined(
        org_id="11932", pp_beginning_cents=2_986_366,
        pp_raised_excl_loans_cents=925_000, pp_loans_cents=0,
        pp_expended_cents=427_824, continuing=cont, has_pre_primary=True,
    )
    assert c.beginning_cents == 2_986_366
    assert c.raised_cents == 4_275_000
    assert c.loans_cents == 0
    assert c.expended_cents == 427_824
    assert c.ending_cents == 6_833_542          # matches combined sheet to the penny
    assert c.identity_ok() is True
    assert "Ending omits continuing-period spending" in c.caveats
    assert c.note.startswith("*Cont. Report - $33500.00")


def test_combined_no_pre_primary():
    c = build_combined("999", None, None, None, None,
                       ContinuingTotal(), has_pre_primary=False)
    assert c.ending_cents == 0
    assert "No Pre-Primary Report" in c.note
    assert c.identity_ok()


def test_large_loan_self_dealing():
    # loan >= raised -> high severity (the brief's "loan larger than raised" check)
    f = flags.large_loan("1", "Derek Porter", raised_cents=500_000, loans_cents=4_000_000)
    assert f and f["type"] == "large_loan" and f["severity"] == "high"
    assert flags.large_loan("1", "x", raised_cents=10_000_000, loans_cents=0) is None


def test_sub_threshold_flag():
    rows = [R("1", dt.date(2026, 6, 5), 50_500, "Monetary", "")]  # $505, Ted Riley case
    out = flags.sub_threshold("1", "Ted Riley", rows, dt.date(2026, 6, 2), dt.date(2026, 6, 16))
    assert len(out) == 1 and out[0]["type"] == "sub_threshold"


def test_amended_and_multiple():
    assert flags.amended_report_used("1", "x", 2)["type"] == "amended_report_used"
    assert flags.amended_report_used("1", "x", 1) is None
    assert flags.multiple_committees("1", "x", ["2", "3"])["type"] == "multiple_committees"
    assert flags.multiple_committees("1", "x", []) is None

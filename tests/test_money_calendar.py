import datetime as dt

from guardian_contrib import money
from guardian_contrib import reporting_calendar as rc


def test_to_cents_variants():
    assert money.to_cents("$29,863.66") == 2986366
    assert money.to_cents("1500") == 150000
    assert money.to_cents("(1,234.56)") == -123456   # parenthesized negative
    assert money.to_cents(" $-   ") is None
    assert money.to_cents("") is None
    assert money.to_cents(None) is None
    # Sign OUTSIDE the parens, both orderings (real deliverable uses "$(...)").
    assert money.to_cents(" $(1,155.47)") == -115547
    assert money.to_cents("($1,155.47)") == -115547


def test_accounting_to_cents_roundtrip():
    for c in (2986366, 0, -115547, -674238, 8650, 150000):
        assert money.to_cents(money.accounting_str(c)) == (c if c != 0 else None)


def test_accounting_and_decimal_roundtrip():
    assert money.accounting_str(2986366) == " $29,863.66 "
    assert money.accounting_str(0) == " $-   "
    assert money.accounting_str(-123456) == " $(1,234.56)"
    assert money.decimal_str(2986366) == "29863.66"
    assert money.decimal_str(-123456) == "-1234.56"
    assert money.decimal_str(None) is None


def test_primary_is_third_tuesday_of_june():
    assert rc.primary_date(2026) == dt.date(2026, 6, 16)   # workflow ground truth
    assert rc.primary_date(2024) == dt.date(2024, 6, 18)
    # always a Tuesday, always in the 15-21 range
    for y in range(2024, 2031):
        p = rc.primary_date(y)
        assert p.weekday() == 1 and 15 <= p.day <= 21


def test_continuing_window_derived_not_hardcoded():
    cal = rc.build_calendar(2026)
    assert cal.continuing_start == dt.date(2026, 6, 2)    # PP end (06/01) + 1
    assert cal.continuing_end == dt.date(2026, 6, 16)     # primary day

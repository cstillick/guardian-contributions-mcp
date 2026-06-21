"""Money handling. Internally everything is integer cents (negatives allowed,
since committee balances can go negative -> formatted with parentheses).

Three representations:
  - cents (int): canonical storage/compute
  - decimal string ("1234.56" / "-1234.56"): API JSON serialization
  - accounting string (" $1,234.56 " / " $-   " / " $(1,234.56)"): Book(Sheet1) CSV parity
"""
from __future__ import annotations


def to_cents(value) -> int | None:
    """Parse a Guardian/extract money token to integer cents.

    Handles '1500', '1500.00', '$1,500.00', '(1,234.56)' (negative), '', None.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s == "-":
        return None
    neg = False
    # Strip the $ first so we catch BOTH "($1,234.56)" and "$(1,234.56)"
    # (Guardian/accounting puts the sign outside the parens).
    s = s.replace("$", "").strip()
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(",", "").strip()
    if s.startswith("-"):
        neg = True
        s = s[1:]
    if s == "":
        return None
    try:
        cents = int(round(float(s) * 100))
    except ValueError:
        return None
    return -cents if neg else cents


def decimal_str(cents: int | None) -> str | None:
    """Serialize cents as a plain decimal string for JSON."""
    if cents is None:
        return None
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def accounting_str(cents: int | None) -> str:
    """Format cents in the Book(Sheet1) accounting convention (CSV-parity).

    Positive ->  ' $1,234.56 '   (leading + trailing space)
    Zero/None -> ' $-   '
    Negative ->  ' $(1,234.56)'
    """
    if cents is None or cents == 0:
        return " $-   "
    neg = cents < 0
    whole, frac = divmod(abs(cents), 100)
    body = f"{whole:,}.{frac:02d}"
    if neg:
        return f" $({body})"
    return f" ${body} "

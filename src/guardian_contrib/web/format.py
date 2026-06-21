"""Jinja filters/helpers for the web layer — display formatting only."""
from __future__ import annotations

FLAG_LABELS = {
    "large_loan": "Self-dealing loan",
    "no_pre_primary": "No Pre-Primary",
    "no_committee": "No committee",
    "multiple_committees": "Multiple committees",
    "sub_threshold": "Sub-$1,000",
    "amended_report_used": "Amended report",
    "identity_mismatch": "Identity mismatch",
    "no_committee_found": "No committee",
}


def fmt_money(cents) -> str:
    """Cents → '$1,234.56' / '($1,234.56)' for negatives / '—' for None."""
    if cents is None:
        return "—"
    neg = cents < 0
    whole, frac = divmod(abs(int(cents)), 100)
    s = f"${whole:,}.{frac:02d}"
    return f"({s})" if neg else s


def fmt_compact(cents) -> str:
    """Compact money for stat cards: $1.2M / $48.3K / $940."""
    if cents is None:
        return "—"
    v = cents / 100
    neg = v < 0
    v = abs(v)
    if v >= 1_000_000:
        out = f"${v / 1_000_000:.1f}M"
    elif v >= 1_000:
        out = f"${v / 1_000:.0f}K"
    else:
        out = f"${v:.0f}"
    return f"-{out}" if neg else out


def fmt_dmoney(s) -> str:
    """Decimal string ('29863.66' / '-1234.56') → '$29,863.66' / '($1,234.56)'."""
    if s is None:
        return "—"
    s = str(s)
    neg = s.startswith("-")
    intpart, _, frac = s.lstrip("-").partition(".")
    frac = (frac + "00")[:2]
    try:
        val = f"${int(intpart):,}.{frac}"
    except ValueError:
        return s
    return f"({val})" if neg else val


def is_negative_d(s) -> bool:
    return bool(s) and str(s).startswith("-")


def flag_label(flag_type: str) -> str:
    return FLAG_LABELS.get(flag_type, flag_type.replace("_", " ").title())


def register(env) -> None:
    env.filters["money"] = fmt_money
    env.filters["compact"] = fmt_compact
    env.filters["dmoney"] = fmt_dmoney
    env.filters["flaglabel"] = flag_label
    env.tests["negative_d"] = is_negative_d

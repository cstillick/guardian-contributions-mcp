"""Combined layering — Section 9. Pre-Primary base + Continuing on top.

Per candidate:
  Beginning = Pre-Primary Beginning
  Expended  = Pre-Primary Expended
  Raised    = Pre-Primary Raised(excl loans) + Continuing Raised
  Loans     = Pre-Primary Loans            + Continuing Loans
  Ending    = Beginning + Raised + Loans − Expended      (recomputed, not PP Ending)

⚠️ Continuing reports carry no expenditures, so Ending omits any spending during
the continuing period — surfaced as a caveat (Rule §9).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..money import decimal_str
from .continuing import ContinuingTotal


@dataclass
class CombinedFigures:
    org_id: str | None
    beginning_cents: int
    raised_cents: int
    loans_cents: int
    expended_cents: int
    ending_cents: int
    pre_primary_raised_cents: int
    pre_primary_loans_cents: int
    continuing_raised_cents: int
    continuing_loans_cents: int
    continuing_count: int
    has_pre_primary: bool
    note: str
    caveats: list[str] = field(default_factory=list)

    def identity_ok(self) -> bool:
        return (
            self.beginning_cents + self.raised_cents + self.loans_cents
            - self.expended_cents
        ) == self.ending_cents

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "beginning": decimal_str(self.beginning_cents),
            "raised": decimal_str(self.raised_cents),
            "loans": decimal_str(self.loans_cents),
            "expended": decimal_str(self.expended_cents),
            "ending": decimal_str(self.ending_cents),
            "continuing_raised": decimal_str(self.continuing_raised_cents),
            "continuing_loans": decimal_str(self.continuing_loans_cents),
            "continuing_count": self.continuing_count,
            "has_pre_primary": self.has_pre_primary,
            "note": self.note,
            "caveats": self.caveats,
            "identity_ok": self.identity_ok(),
        }


def _note(continuing: ContinuingTotal, has_pp: bool, extra: list[str]) -> str:
    parts: list[str] = []
    if continuing.raised_cents or continuing.loans_cents:
        note = f"*Cont. Report - ${decimal_str(continuing.raised_cents)}"
        if continuing.loans_cents:
            note += f"; ${decimal_str(continuing.loans_cents)} loan"
        parts.append(note)
    if not has_pp:
        parts.append("No Pre-Primary Report")
    parts.extend(extra)
    return "; ".join(parts)


def build_combined(
    org_id: str | None,
    pp_beginning_cents: int | None,
    pp_raised_excl_loans_cents: int | None,
    pp_loans_cents: int | None,
    pp_expended_cents: int | None,
    continuing: ContinuingTotal,
    has_pre_primary: bool,
    extra_notes: list[str] | None = None,
) -> CombinedFigures:
    beginning = pp_beginning_cents or 0
    pp_raised = pp_raised_excl_loans_cents or 0
    pp_loans = pp_loans_cents or 0
    expended = pp_expended_cents or 0

    raised = pp_raised + continuing.raised_cents
    loans = pp_loans + continuing.loans_cents
    ending = beginning + raised + loans - expended

    caveats: list[str] = []
    if continuing.raised_cents or continuing.loans_cents:
        caveats.append("Ending omits continuing-period spending")

    return CombinedFigures(
        org_id=org_id,
        beginning_cents=beginning,
        raised_cents=raised,
        loans_cents=loans,
        expended_cents=expended,
        ending_cents=ending,
        pre_primary_raised_cents=pp_raised,
        pre_primary_loans_cents=pp_loans,
        continuing_raised_cents=continuing.raised_cents,
        continuing_loans_cents=continuing.loans_cents,
        continuing_count=continuing.count,
        has_pre_primary=has_pre_primary,
        note=_note(continuing, has_pre_primary, extra_notes or []),
        caveats=caveats,
    )

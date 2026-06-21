"""Normalized store schema (SQLAlchemy 2.0).

Stable so the API never re-parses on read. Money is integer cents. Multi-cycle
from day one (cycle_year on the cycle-scoped tables). Mirrors Section 6 of the
design spec.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Committee(Base):
    __tablename__ = "committees"

    org_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(256), default="")  # committee legal name
    candidate_name: Mapped[str | None] = mapped_column(String(256), index=True)  # Guardian's
    roster_name: Mapped[str | None] = mapped_column(String(256))      # caller-supplied label
    committee_type: Mapped[str | None] = mapped_column(String(64))  # Candidate/PAC/Party/...
    district: Mapped[str | None] = mapped_column(String(16))        # e.g. HD-42, SD-15
    office: Mapped[str | None] = mapped_column(String(64))          # Representative/Senator/...
    party: Mapped[str | None] = mapped_column(String(8))            # (D)/(R)/...
    election_cycle: Mapped[str | None] = mapped_column(String(64))  # "2026 NOVEMBER GENERAL"
    cycle_year: Mapped[int | None] = mapped_column(Integer, index=True)
    status: Mapped[str | None] = mapped_column(String(32))
    # Rule 6: resolved once at ingest — the regular-cycle (Nov General) committee,
    # not a Special-Election committee for the same person.
    is_regular_cycle: Mapped[bool] = mapped_column(Boolean, default=True)

    receipts: Mapped[list["Receipt"]] = relationship(back_populates="committee")
    reports: Mapped[list["Report"]] = relationship(back_populates="committee")


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("cycle_year", "receipt_id", name="uq_receipt_cycle"),
        Index("ix_receipt_org_date", "org_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_year: Mapped[int] = mapped_column(Integer, index=True)
    receipt_id: Mapped[str] = mapped_column(String(32), index=True)
    org_id: Mapped[str] = mapped_column(String(16), ForeignKey("committees.org_id"), index=True)
    date: Mapped[dt.date | None] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    receipt_type: Mapped[str | None] = mapped_column(String(64))   # Monetary/In-Kind/Loan/...
    source_type: Mapped[str | None] = mapped_column(String(64))    # Individual/PAC/Party/...
    source_name: Mapped[str | None] = mapped_column(String(256))
    city: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str | None] = mapped_column(String(8))
    zip: Mapped[str | None] = mapped_column(String(16))
    filed_date: Mapped[dt.date | None] = mapped_column(Date)
    amended: Mapped[str | None] = mapped_column(String(2))         # Y / N / ''
    description: Mapped[str | None] = mapped_column(Text)

    committee: Mapped["Committee"] = relationship(back_populates="receipts")


class Report(Base):
    __tablename__ = "reports"

    filing_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(16), ForeignKey("committees.org_id"), index=True)
    cycle_year: Mapped[int | None] = mapped_column(Integer, index=True)
    report_type: Mapped[str | None] = mapped_column(String(128))   # "2026 PRE-PRIMARY REPORT"
    report_class: Mapped[str | None] = mapped_column(String(16))   # 'periodic' | 'itemized'
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    period_end: Mapped[dt.date | None] = mapped_column(Date)
    filed_date: Mapped[dt.date | None] = mapped_column(Date)
    amended: Mapped[bool] = mapped_column(Boolean, default=False)
    is_latest_version: Mapped[bool] = mapped_column(Boolean, default=True)  # Rule 8
    source_pdf_path: Mapped[str | None] = mapped_column(String(512))

    committee: Mapped["Committee"] = relationship(back_populates="reports")
    summary: Mapped["Summary"] = relationship(back_populates="report", uselist=False)


class Summary(Base):
    """Schedule Summary figures, Reporting-Period column (Rule 6). filing_id 1:1."""

    __tablename__ = "summaries"

    filing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("reports.filing_id"), primary_key=True
    )
    beginning_cents: Mapped[int | None] = mapped_column(Integer)
    total_received_cents: Mapped[int | None] = mapped_column(Integer)
    loans_cents: Mapped[int | None] = mapped_column(Integer)
    expended_cents: Mapped[int | None] = mapped_column(Integer)
    ending_cents: Mapped[int | None] = mapped_column(Integer)

    report: Mapped["Report"] = relationship(back_populates="summary")

    @property
    def raised_excl_loans_cents(self) -> int | None:
        if self.total_received_cents is None or self.loans_cents is None:
            return None
        return self.total_received_cents - self.loans_cents


class Run(Base):
    """Append-only ingestion run log (Rule 10/11/13: as-of + freshness gate)."""

    __tablename__ = "runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime)
    cycle_year: Mapped[int] = mapped_column(Integer, index=True)
    max_filed_date: Mapped[dt.date | None] = mapped_column(Date)
    max_receipt_date: Mapped[dt.date | None] = mapped_column(Date)
    primary_date: Mapped[dt.date | None] = mapped_column(Date)
    pre_primary_start: Mapped[dt.date | None] = mapped_column(Date)
    pre_primary_end: Mapped[dt.date | None] = mapped_column(Date)
    continuing_start: Mapped[dt.date | None] = mapped_column(Date)
    continuing_end: Mapped[dt.date | None] = mapped_column(Date)
    extract_rows: Mapped[int | None] = mapped_column(Integer)
    changed_since_prev: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("runs.run_id"), index=True)
    org_id: Mapped[str | None] = mapped_column(String(16), index=True)
    candidate: Mapped[str | None] = mapped_column(String(256))
    type: Mapped[str] = mapped_column(String(48))       # large_loan, sub_threshold, ...
    severity: Mapped[str] = mapped_column(String(16))   # info | warn | high
    detail: Mapped[str | None] = mapped_column(Text)

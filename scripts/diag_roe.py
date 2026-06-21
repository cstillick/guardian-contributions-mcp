"""Diagnostic: reconcile the Cindy Roe Pre-Primary parse against ground truth.

Ground truth = the known-good combined sheet. Continuing raised is known to be
$33,500 (verified by both the workflow doc and our bulk spike), so:
    Pre-Primary Raised = combined Raised - 33,500
    Pre-Primary Beginning = combined Beginning   (combined Beginning IS the PP Beginning)
    Pre-Primary Expended  = combined Expended     (continuing carries no spend)

We then dump the raw Schedule Summary lines from BOTH the live-fetched PDF and the
local saved PDF to see column ordering and which one is the real 2026 report.
"""
import csv
import io
import os
import re
import sys

import httpx
from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(__file__))
from spike_pdf_chain import get_report, pdf_text  # reuse the proven chain

CSV = "../Ok_preprimary_and_continuing_reports_2.csv"
LOCAL = "../Pre-Primary Reports/HD42_Cindy_Roe_2026_Pre-Primary.pdf"
KEYS = ["BEGINNING BALANCE", "TOTAL FUNDS RECEIVED", "Loans [Schedule C]",
        "TOTAL FUNDS EXPENDED", "ENDING BALANCE"]


def show_csv_truth():
    print("=== ground truth from combined sheet ===")
    with open(CSV, newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and "roe" in row[1].lower():
                print("  row:", row[:7])


def dump_summary(tag, text):
    print(f"\n=== {tag}: raw Schedule Summary context ===")
    lines = [l.strip() for l in text.splitlines()]
    for k in KEYS:
        for i, l in enumerate(lines):
            if k.upper() in l.upper():
                print(f"  [{k:22}] next4 -> {lines[i + 1:i + 5]}")
                break
        else:
            print(f"  [{k:22}] NOT FOUND")


def main():
    show_csv_truth()

    if os.path.exists(LOCAL):
        with open(LOCAL, "rb") as fh:
            local_text = pdf_text(fh.read())
        dump_summary("LOCAL saved PDF", local_text)
        print("  type-of-report line(s):",
              [l.strip() for l in local_text.splitlines() if "PRE-PRIMARY" in l.upper() or "QUARTER" in l.upper()][:3])

    print("\nfetching live ...")
    pdf = get_report("11932", r"PRE-PRIMARY")
    with open("scripts/_live_roe_pp.pdf", "wb") as fh:
        fh.write(pdf)
    live_text = pdf_text(pdf)
    dump_summary("LIVE fetched PDF", live_text)
    print("  type-of-report line(s):",
          [l.strip() for l in live_text.splitlines() if "PRE-PRIMARY" in l.upper() or "QUARTER" in l.upper()][:3])


if __name__ == "__main__":
    main()

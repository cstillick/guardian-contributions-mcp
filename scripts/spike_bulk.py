"""Phase-0 spike: download + parse the live Guardian bulk contribution/loan extract.

Proves: (1) the zip is reachable and downloadable from a plain Python process,
(2) the Appendix-A record-split parser handles the real file (23 fields, stray
quotes), (3) freshness probe (max Filed/Receipt date), (4) characterizes every
Committee Type and the blank-Org-ID rows so the "all committee types" scope is
grounded in real data rather than assumption.

Run:  uv run --with httpx --with pypdf --no-project python scripts/spike_bulk.py
"""
import io
import re
import sys
import zipfile
import datetime as dt
from collections import Counter

import httpx

YEAR = 2026
URL = f"https://guardian.ok.gov/PublicSite/Docs/BulkDataDownloads/{YEAR}_ContributionLoanExtract.csv.zip"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"}


def download() -> bytes:
    with httpx.Client(timeout=120.0, headers=UA, follow_redirects=True) as c:
        r = c.get(URL)
        r.raise_for_status()
        return r.content


def parse_records(text: str):
    """Appendix A: split records on \\r?\\n(?="), strip outer quotes, split on '","'."""
    recs = re.split(r'\r?\n(?=")', text)

    def fields(rec: str):
        s = rec.rstrip("\r")
        if s.startswith('"'):
            s = s[1:]
        if s.endswith('"'):
            s = s[:-1]
        return s.split('","')

    header = fields(recs[0])
    idx = {h.strip(): i for i, h in enumerate(header)}
    rows, bad = [], 0
    for rec in recs[1:]:
        if not rec.strip():
            continue
        f = fields(rec)
        if len(f) == len(header):
            rows.append(f)
        else:
            bad += 1
    return header, idx, rows, bad


def to_date(v: str):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", v or "")
    return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def main():
    print(f"GET {URL}")
    try:
        raw = download()
    except Exception as e:
        print("DOWNLOAD FAILED:", repr(e))
        sys.exit(1)
    print(f"  zip bytes: {len(raw):,}")

    z = zipfile.ZipFile(io.BytesIO(raw))
    name = z.namelist()[0]
    text = z.read(name).decode("utf-8", errors="replace")
    print(f"  csv: {name}  chars: {len(text):,}")

    header, idx, rows, bad = parse_records(text)
    print(f"\nheader fields: {len(header)}  (expect 23)")
    print(f"data rows: {len(rows):,}   malformed dropped: {bad}")
    missing = [c for c in ("Receipt ID", "Org ID", "Receipt Type", "Receipt Date",
                           "Receipt Amount", "Committee Type", "Filed Date", "Amended") if c not in idx]
    print("missing expected columns:", missing or "none")

    # Freshness probe (Rule 13)
    fd = [d for d in (to_date(r[idx["Filed Date"]]) for r in rows) if d]
    rd = [d for d in (to_date(r[idx["Receipt Date"]]) for r in rows) if d]
    print(f"\nmax Filed Date:   {max(fd)}")
    print(f"max Receipt Date: {max(rd)}")

    # Committee-type characterization (the 'all types' scope grounding)
    print("\nCommittee Type counts:")
    for k, v in Counter(r[idx["Committee Type"]] for r in rows).most_common():
        print(f"   {v:>8,}  {k!r}")

    # Blank Org ID rows (Rule 14 — these are where PAC/state-question live)
    blank = [r for r in rows if not r[idx["Org ID"]].strip()]
    print(f"\nblank Org ID rows: {len(blank):,}")
    for r in blank[:8]:
        print(f"   type={r[idx['Committee Type']]!r:24} name={r[idx['Committee Name']]!r:34} "
              f"rcpt={r[idx['Receipt Type']]!r:18} amt={r[idx['Receipt Amount']]}")

    # Dedup guard among real committee rows
    rid = Counter(r[idx["Receipt ID"]] for r in rows
                  if r[idx["Org ID"]].strip() and r[idx["Receipt ID"]].strip())
    dups = [k for k, v in rid.items() if v > 1]
    print(f"\nduplicate Receipt IDs (non-blank Org ID): {len(dups)}")

    # Continuing-window slice (>= 06/02)
    cw = [r for r in rows if (to_date(r[idx["Receipt Date"]]) or dt.date(1900, 1, 1)) >= dt.date(2026, 6, 2)]
    print(f"receipts dated >= 2026-06-02: {len(cw):,}")

    # Spot the Cindy Roe committee (11932) continuing receipts
    roe = [r for r in cw if r[idx["Org ID"]].strip() == "11932" and r[idx["Amended"]] != "Y"]
    print(f"\nOrg 11932 (Cindy Roe) receipts >= 06/02: {len(roe)}")
    for r in roe[:12]:
        print(f"   {r[idx['Receipt Date']]:12} {r[idx['Receipt Type']]:16} "
              f"{r[idx['Receipt Amount']]:>12}  rid={r[idx['Receipt ID']]}")

    print("\nSPIKE OK")


if __name__ == "__main__":
    main()

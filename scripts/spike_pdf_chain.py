"""Phase-0 spike: retrieve ONE report PDF via the ASP.NET postback chain, in pure
Python (httpx), and parse its Schedule Summary.

This is the make-or-break piece. It ports Appendix B (browser pdf.js) to a
server-side httpx session: persistent cookies + viewstate, sequential POSTs,
then FetchReportToPDF.aspx. Acceptance: get %PDF- bytes for an org and parse a
Schedule Summary; compare to the matching local PDF to the penny.

Run:  uv run --with httpx --with pypdf --no-project python scripts/spike_pdf_chain.py [ORG_ID] [REPORT_REGEX]
Default: ORG_ID=11932 (Cindy Roe), REPORT_REGEX=PRE-PRIMARY
"""
import io
import os
import re
import sys
import glob

import httpx
from pypdf import PdfReader

BASE = "https://guardian.ok.gov/PublicSite"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"}


def hidden_fields(html: str) -> dict:
    out = {}
    for m in re.finditer(r"<input[^>]*type=\"hidden\"[^>]*>", html, re.I):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            out[n.group(1)] = v.group(1) if v else ""
    return out


def _num(x):
    if x is None:
        return None
    x = x.replace(",", "").replace("$", "").strip()
    m = re.match(r"^\((.*)\)$", x)
    if m:
        return -float(m.group(1))
    return float(x)


def parse_summary(text: str) -> dict:
    def find(pat):
        m = re.search(pat, text)
        return m.group(1) if m else None

    beg = _num(find(r"BEGINNING BALANCE:\s*(\(?\$?[\d,]+\.\d{2}\)?)"))
    recv = _num(find(r"TOTAL FUNDS RECEIVED:\s*\$?([\d,]+\.\d{2})"))
    loan = _num(find(r"7a\.\s*Loans \[Schedule C\]\s*\$?([\d,]+\.\d{2})"))
    exp = _num(find(r"TOTAL FUNDS EXPENDED:\s*\$?([\d,]+\.\d{2})"))
    end = _num(find(r"ENDING BALANCE:\s*(\(?\$?[\d,]+\.\d{2}\)?)"))
    return {
        "office_district": find(r"((?:REPRESENTATIVE|SENATE|SENATOR)[^\n]*DISTRICT\s*\d+)"),
        "district": find(r"DISTRICT\s*(\d+)"),
        "period": find(r"(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4})"),
        "amended": find(r"AMENDED:\s*(YES|NO)"),
        "type_of_report": find(r"Type of Report[:\s]*([A-Z][A-Za-z \-/]+)"),
        "beginning": beg,
        "total_received": recv,
        "loans": loan,
        "expended": exp,
        "ending": end,
        "raised_excl_loans": (recv - loan) if (recv is not None and loan is not None) else None,
    }


def pdf_text(data: bytes) -> str:
    r = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def get_report(org_id: str, want: str = r"PRE-PRIMARY") -> bytes | None:
    detail = f"{BASE}/SearchPages/OrganizationDetail.aspx?OrganizationID={org_id}"
    with httpx.Client(timeout=90.0, headers=UA, follow_redirects=True) as c:
        h1 = c.get(detail).text
        anchors = [(m.group(1), m.group(2).strip()) for m in re.finditer(
            r'id="(ctl00_Content_dgdFilingHistory_ctl\d+_lnkFilingHist)"[^>]*>([^<]+)<', h1)]
        print(f"filing-history anchors: {len(anchors)}")
        for a in anchors[:12]:
            print("   ", a[1])
        if not anchors:
            print("!! no filing-history anchors found — page shape differs")
            return None
        tgt = next((a for a in anchors if re.search(want, a[1], re.I)), None)
        if not tgt:
            print(f"!! no anchor matching /{want}/")
            return None
        print("target report:", tgt[1], "  id:", tgt[0])

        # POST 1 -> FilingAmendmentSelect
        f1 = hidden_fields(h1)
        f1["__EVENTTARGET"] = tgt[0].replace("_", "$")
        f1["__EVENTARGUMENT"] = ""
        r2 = c.post(detail, data=f1, headers={"Referer": detail})
        url2, h2 = str(r2.url), r2.text
        print("after POST1 ->", url2)

        # POST 2 -> select latest/amended version (last lnkView)
        views = re.findall(r'id="(ctl00_Content_grdAmendments_ctl\d+_lnkView)"', h2, re.I)
        print(f"amendment 'lnkView' rows: {len(views)}  -> taking last = {views[-1] if views else None}")
        if views:
            f2 = hidden_fields(h2)
            f2["__EVENTTARGET"] = views[-1].replace("_", "$")
            f2["__EVENTARGUMENT"] = ""
            c.post(url2, data=f2, headers={"Referer": url2})  # sets session state

        # GET the PDF (relies on session state from POST 2)
        pdf = c.get(f"{BASE}/Reports/FetchReportToPDF.aspx", headers={"Referer": url2}).content
        print(f"FetchReportToPDF bytes: {len(pdf):,}  head={pdf[:8]!r}")
        if not pdf.startswith(b"%PDF"):
            print("!! not a PDF; first 300 bytes:\n", pdf[:300])
            return None
        return pdf


def main():
    org = sys.argv[1] if len(sys.argv) > 1 else "11932"
    want = sys.argv[2] if len(sys.argv) > 2 else r"PRE-PRIMARY"
    print(f"=== retrieving org {org} report matching /{want}/ ===")
    try:
        pdf = get_report(org, want)
    except Exception as e:
        print("CHAIN FAILED:", repr(e))
        sys.exit(1)
    if not pdf:
        print("FAILED to retrieve PDF")
        sys.exit(1)

    live = parse_summary(pdf_text(pdf))
    print("\nLIVE parsed Schedule Summary:")
    for k, v in live.items():
        print(f"   {k:20} {v}")

    # Compare to the matching local PDF if present
    for pat in ("../Pre-Primary Reports/HD42_Cindy_Roe_2026_Pre-Primary.pdf",
                "Pre-Primary Reports/HD42_Cindy_Roe_2026_Pre-Primary.pdf"):
        hits = glob.glob(pat)
        if hits:
            with open(hits[0], "rb") as fh:
                loc = parse_summary(pdf_text(fh.read()))
            print(f"\nLOCAL ({os.path.basename(hits[0])}) parsed:")
            for k in ("beginning", "total_received", "loans", "expended", "ending", "raised_excl_loans"):
                match = "OK " if live.get(k) == loc.get(k) else "DIFF"
                print(f"   {match} {k:20} live={live.get(k)}  local={loc.get(k)}")
            break

    print("\nSPIKE OK — postback chain + PDF parse working")


if __name__ == "__main__":
    main()

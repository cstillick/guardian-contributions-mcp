"""Guardian HTTP client — the ASP.NET postback chain (Section 4B/4C), in pure
httpx. Proven end-to-end in the Phase-0 spike.

Report PDF retrieval is sequential by construction (Rule 4: the FetchReportToPDF
handler depends on session state set by the immediately-preceding POST — parallel
fetches collide). Callers loop; each fetch re-navigates from OrganizationDetail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from ..config import Settings


@dataclass
class Filing:
    anchor_id: str
    label: str
    index: int


@dataclass
class CommitteeDetail:
    org_id: str
    legal_name: str
    office: str | None
    district: str | None          # normalized: HD-42 / SD-15 / None
    district_raw: str | None      # "DISTRICT 42"
    party: str | None             # (D)/(R)/...
    election: str | None          # "2026 NOVEMBER GENERAL ELECTION"
    election_cycle: str | None
    status: str | None
    is_regular_cycle: bool
    cycle_year: int | None


@dataclass
class ReportFetch:
    pdf: bytes
    filing_id: str | None
    label: str
    version_count: int


_HIDDEN_RE = re.compile(r"<input[^>]*type=\"hidden\"[^>]*>", re.I)
_SPAN_RE = re.compile(r"<span[^>]*id=\"([^\"]+)\"[^>]*>(.*?)</span>", re.S)
_FILING_RE = re.compile(
    r"id=\"(ctl00_Content_dgdFilingHistory_ctl\d+_lnkFilingHist)\"[^>]*>([^<]+)<"
)
_VIEW_RE = re.compile(r"id=\"(ctl00_Content_grdAmendments_ctl\d+_lnkView)\"", re.I)


def _hidden_fields(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _HIDDEN_RE.finditer(html):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            out[n.group(1)] = v.group(1) if v else ""
    return out


def _spans(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for sid, raw in _SPAN_RE.findall(html):
        key = sid.split("_")[-1]
        val = re.sub(r"<[^>]+>", "", raw).strip()
        if val and key not in out:  # first non-empty wins
            out[key] = val
    return out


def normalize_district(office: str | None, district_raw: str | None) -> str | None:
    if not district_raw:
        return None
    m = re.search(r"(\d+)", district_raw)
    if not m:
        return None
    n = m.group(1)
    o = (office or "").upper()
    if "REPRESENT" in o:
        return f"HD-{n}"
    if "SENAT" in o:
        return f"SD-{n}"
    return f"D-{n}"


def normalize_party(party_raw: str | None) -> str | None:
    if not party_raw:
        return None
    u = party_raw.upper()
    if u.startswith("REPUB"):
        return "(R)"
    if u.startswith("DEMOCRAT"):
        return "(D)"
    if u.startswith("INDEP"):
        return "(I)"
    if u.startswith("LIBERT"):
        return "(L)"
    return f"({party_raw[:1].upper()})"


class GuardianClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.base = settings.guardian_base
        self._http = httpx.Client(
            timeout=settings.request_timeout,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )

    def __enter__(self) -> "GuardianClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- raw pages -------------------------------------------------------
    def _detail_url(self, org_id: str) -> str:
        return f"{self.base}/SearchPages/OrganizationDetail.aspx?OrganizationID={org_id}"

    def organization_detail_html(self, org_id: str) -> str:
        return self._http.get(self._detail_url(org_id)).text

    # --- filings ---------------------------------------------------------
    def list_filings(self, org_id: str, html: str | None = None) -> list[Filing]:
        html = html or self.organization_detail_html(org_id)
        return [
            Filing(anchor_id=m.group(1), label=m.group(2).strip(), index=i)
            for i, m in enumerate(_FILING_RE.finditer(html))
        ]

    # --- committee detail (Rule 5 district, Rule 6 regular-cycle) --------
    def committee_detail(self, org_id: str, html: str | None = None) -> CommitteeDetail:
        html = html or self.organization_detail_html(org_id)
        sp = _spans(html)
        office = sp.get("lblCandOffice")
        district_raw = sp.get("lblCandDistrict")
        election = sp.get("lblElection")
        cycle = sp.get("lblElectionCycle")
        is_regular = bool(election) and "SPECIAL" not in election.upper()
        cycle_year = None
        if election:
            ym = re.search(r"(20\d{2})", election)
            cycle_year = int(ym.group(1)) if ym else None
        return CommitteeDetail(
            org_id=org_id,
            legal_name=sp.get("lblCandName", ""),
            office=office,
            district=normalize_district(office, district_raw),
            district_raw=district_raw,
            party=normalize_party(sp.get("lblPartyAffiliationValue")),
            election=election,
            election_cycle=cycle,
            status=sp.get("lblCandStatus"),
            is_regular_cycle=is_regular,
            cycle_year=cycle_year,
        )

    # --- report PDF retrieval (the postback chain) -----------------------
    def fetch_report(self, org_id: str, want: str = r"PRE-PRIMARY",
                     anchor: str | None = None) -> ReportFetch | None:
        detail = self._detail_url(org_id)
        h1 = self._http.get(detail).text
        anchors = [(m.group(1), m.group(2).strip()) for m in _FILING_RE.finditer(h1)]
        if anchor is not None:
            tgt = next((a for a in anchors if a[0] == anchor), None)
        else:
            tgt = next((a for a in anchors if re.search(want, a[1], re.I)), None)
        if not tgt:
            return None

        f1 = _hidden_fields(h1)
        f1["__EVENTTARGET"] = tgt[0].replace("_", "$")
        f1["__EVENTARGUMENT"] = ""
        r2 = self._http.post(detail, data=f1, headers={"Referer": detail})
        url2, h2 = str(r2.url), r2.text
        fm = re.search(r"FilingID=(\d+)", url2)
        filing_id = fm.group(1) if fm else None

        views = _VIEW_RE.findall(h2)
        if views:
            f2 = _hidden_fields(h2)
            f2["__EVENTTARGET"] = views[-1].replace("_", "$")  # Rule 8: latest/amended
            f2["__EVENTARGUMENT"] = ""
            self._http.post(url2, data=f2, headers={"Referer": url2})

        pdf = self._http.get(
            f"{self.base}/Reports/FetchReportToPDF.aspx", headers={"Referer": url2}
        ).content
        if not pdf.startswith(b"%PDF"):
            return None
        return ReportFetch(pdf=pdf, filing_id=filing_id, label=tgt[1], version_count=len(views))

    # --- candidate search (Section 4C) — best-effort name->org_id --------
    def search_candidates(self, last_name: str, first_name: str = "") -> list[dict]:
        url = f"{self.base}/SearchPages/CandidateSearch.aspx"
        try:
            h0 = self._http.get(url).text
        except httpx.HTTPError:
            return []
        fields = _hidden_fields(h0)
        # Field names vary; fill any LastName/FirstName textboxes we can find.
        for name in re.findall(r'name="([^"]*LastName[^"]*)"', h0):
            fields[name] = last_name
        for name in re.findall(r'name="([^"]*FirstName[^"]*)"', h0):
            fields[name] = first_name
        btn = re.search(r'name="([^"]*SearchButton[^"]*)"', h0)
        if btn:
            fields[btn.group(1)] = "Search"
        h1 = self._http.post(url, data=fields, headers={"Referer": url}).text
        out = []
        for m in re.finditer(r"OrganizationDetail\.aspx\?OrganizationID=(\d+)", h1):
            out.append({"org_id": m.group(1)})
        # dedupe
        seen, uniq = set(), []
        for r in out:
            if r["org_id"] not in seen:
                seen.add(r["org_id"])
                uniq.append(r)
        return uniq

    # --- bulk ------------------------------------------------------------
    def download_bulk(self, year: int | None = None) -> bytes:
        r = self._http.get(self.s.bulk_url(year))
        r.raise_for_status()
        return r.content

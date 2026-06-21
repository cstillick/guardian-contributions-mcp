"""2026 working roster + curated name→Org-ID resolution (workflow Section 12).

Rule 5: match by Org ID, never fuzzy. The curated overrides below are the
authoritative, already-verified resolutions (incl. the regular-cycle committee
for people who also have a Special-Election committee — Rule 6). Names not in the
overrides are resolved from the bulk extract's Candidate Name field at ingest.
"""
from __future__ import annotations

import re
import unicodedata

# District -> candidates (typos preserved deliberately — they match the deliverable).
ROSTER_2026: dict[str, list[str]] = {
    "HD-35": ["Dillon Travis", "Kevin Wright"],
    "HD-37": ["John George", "Jenni White", "Joe Nelson"],
    "HD-42": ["Cindy Roe", "Kaity Keith"],
    "HD-52": ["Cody Elliott", "Cole Stevens"],
    "HD-53": ["Jason Blair", "Grant Worley", "Carroll Asseo"],
    "HD-65": ["Sam Mitchell", "Carla Weaver"],
    "HD-69": ["Sheila Dills", "Sngela Strohm", "Carrie DeWeese", "Cody Nichols", "Tyler Price"],
    "HD-73": ["Ron Stewart", "Ed Ross"],
    "HD-74": ["Kevin Norwood", "Sheila Vancuren", "Aaron Brent"],
    "HD-86": ["David Hardin", "Ryan Martin", "Hannah Cole"],
    "HD-91": ["Roberto Seda", "Michael Freeman", "Teresa Sterling",
              "Bruce Fleming", "Debbie Shultz", "Chris Fowler"],
    "HD-97": ["Aletia Timmons", "Chimere Grant"],
    "HD-98": ["Gabe Woolley", "Dean Davis", "Cathy Smythe"],
    "HD-99": ["Melvin Latham", "Herschel Brown", "Derrick Sier",
              "Alan Washington", "Carlos Robinson", "Steve Davis"],
}

# roster label -> Org ID (regular-cycle committee). Section 12.
ORG_OVERRIDES: dict[str, str] = {
    "cindy roe": "11932", "cynthia roe": "11932",
    "ron stewart": "12179", "kevin norwood": "12260", "david hardin": "12153",
    "aletia timmons": "11957", "dillon travis": "12300", "jeremy sacket": "11782",
    "spencer grance": "11826", "spencer grace": "11826", "roberto seda": "11855",
    "roberta seda": "11855", "herschel brown": "12339", "ed ross": "12343",
    "george phipps": "12229", "geroge phipps": "12229", "sheila venuren": "12382",
    "sheila vancuren": "12382", "megan hombeek": "12281", "megan hornbeek": "12281",
    "megan hornbeek allen": "12281", "sam wargin grimaldo": "11938",
    "vicki werneke": "12304",
}

# Known committee with a Special-Election sibling (regular -> special). Rule 6.
SPECIAL_SIBLINGS: dict[str, str] = {"11938": "12315", "12304": "12301"}

NO_COMMITTEE_2026 = {"amber ellis", "cuen funderburke", "casey sutterfield", "grant worley"}
NO_PRE_PRIMARY_2026 = {"scotty stokes": "11870", "shelton foster": "11850"}


def norm_name(name: str) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace — for matching only."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def all_roster_candidates() -> list[tuple[str, str]]:
    """[(district, candidate_name), ...] for the embedded 2026 roster."""
    return [(d, c) for d, cands in ROSTER_2026.items() for c in cands]


def resolve_org_id(name: str, bulk_name_index: dict[str, list[str]] | None = None) -> dict:
    """Resolve a roster name to org_id(s).

    Returns {org_id, candidates:[...all matches...], source, multiple:bool}.
    Override map wins (verified). Otherwise consult a {normalized_candidate_name ->
    [org_ids]} index built from the bulk extract. Never fuzzy (Rule 5).
    """
    key = norm_name(name)
    if key in ORG_OVERRIDES:
        oid = ORG_OVERRIDES[key]
        return {"org_id": oid, "candidates": [oid], "source": "override", "multiple": False}
    if key in NO_PRE_PRIMARY_2026:
        oid = NO_PRE_PRIMARY_2026[key]
        return {"org_id": oid, "candidates": [oid], "source": "no_pre_primary", "multiple": False}
    if key in NO_COMMITTEE_2026:
        return {"org_id": None, "candidates": [], "source": "no_committee", "multiple": False}
    matches = (bulk_name_index or {}).get(key, [])
    return {
        "org_id": matches[0] if len(matches) == 1 else None,
        "candidates": matches,
        "source": "bulk" if matches else "unresolved",
        "multiple": len(matches) > 1,
    }

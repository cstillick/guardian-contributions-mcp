"""Name resolution: order-independent + nickname-aware, but never last-name-only."""
from guardian_contrib.roster import build_name_index, canon_tokens, resolve_org_id


def test_canon_tokens_reorder_nickname_and_initials():
    assert canon_tokens("ROE, CYNTHIA JO") == frozenset({"roe", "cynthia", "jo"})
    assert canon_tokens("Cindy Roe") == frozenset({"cynthia", "roe"})       # nickname
    assert canon_tokens("Steven R Davis") == frozenset({"steven", "davis"})  # initial dropped


def test_resolves_last_first_format():
    idx = build_name_index([("55555", "GRANT, CHIMERE D"), ("66666", "GREEN, GRANT")])
    r = resolve_org_id("Chimere Grant", idx)
    assert r["org_id"] == "55555" and r["source"] == "name"  # not the GREEN, GRANT committee


def test_resolves_nickname():
    idx = build_name_index([("88888", "DAVIS, STEVEN R")])
    assert resolve_org_id("Steve Davis", idx)["org_id"] == "88888"


def test_rule5_no_last_name_only_false_positive():
    # Roy Timmons must NOT match Aletia Timmons (the documented false positive).
    idx = build_name_index([("77777", "TIMMONS, ALETIA HAYNES")])
    r = resolve_org_id("Roy Timmons", idx)
    assert r["org_id"] is None and r["candidates"] == []


def test_two_same_name_committees_flag_multiple():
    idx = build_name_index([("1", "SMITH, JOHN"), ("2", "SMITH, JOHN A")])
    r = resolve_org_id("John Smith", idx)
    assert r["org_id"] is None and r["multiple"] is True and set(r["candidates"]) == {"1", "2"}


def test_override_still_wins():
    # Cynthia/Cindy Roe is pinned to the verified 2026 committee regardless of index.
    assert resolve_org_id("Cindy Roe", [])["org_id"] == "11932"

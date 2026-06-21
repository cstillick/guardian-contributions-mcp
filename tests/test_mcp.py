"""MCP server: tools are registered with schemas, and a tool call returns the
penny-accurate combined figure (the thin adapter is wired to the service layer)."""
import json

from conftest import seed_roe_store

EXPECTED_TOOLS = {
    "search_candidates", "get_committee", "list_district_candidates", "list_filings",
    "get_report", "get_summary", "get_contributions", "get_continuing",
    "get_combined", "get_flags", "get_calendar", "refresh_status", "query",
}


async def test_all_tools_registered(temp_db):
    from guardian_contrib.mcp_server import server
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS <= names, f"missing: {EXPECTED_TOOLS - names}"
    # each tool exposes an input schema
    assert all(t.inputSchema is not None for t in tools)


async def test_call_get_combined(temp_db):
    seed_roe_store()
    from guardian_contrib.mcp_server import server
    result = await server.mcp.call_tool("get_combined", {"org_id": "11932"})
    blob = json.dumps(result, default=lambda o: getattr(o, "__dict__", str(o)))
    assert "68335.42" in blob and "33500.00" in blob


def test_tool_functions_callable_directly(temp_db):
    # FastMCP returns the original fn, so the wrappers are plain callables too.
    seed_roe_store()
    from guardian_contrib.mcp_server import server
    out = server.get_combined(org_id="11932")
    assert out["ending"] == "68335.42"
    cal = server.get_calendar(2026)
    assert cal["primary_date"] == "2026-06-16"

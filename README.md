# Guardian Contributions — MCP + API

A reusable service that turns the manual **Oklahoma Campaign-Finance Combined
Reports** workflow (Pre-Primary + Continuing) into:

- a backend **REST API** that pulls and normalizes Oklahoma Ethics Commission
  *Guardian* data, and
- an **MCP** front-end that lets a client (Claude or any MCP host) *select
  between categories* — politician/race (who) × financial/contribution (what) —
  to retrieve the contribution information the workflow produces by hand today.

Source of truth for the business rules is `../Continuing_Reports_Workflow_Instructions.md`
(the 14 Hard Rules). Every rule is enforced as a service invariant (see below) and
backed by a test. The headline acceptance check holds: a fresh pull reproduces the
known-good June figures **to the penny** (e.g. HD-42 Cynthia Roe: Beginning
$29,863.66 + Raised $42,750.00 − Expended $4,278.24 = Ending $68,335.42).

---

## Architecture

```
MCP host (Claude)  ──tools──▶  MCP server ─┐
                                           ├─▶  service layer  ─▶  normalized store
REST client        ──HTTP───▶  FastAPI ────┘     (one place         (SQLite / Postgres)
                                                  the rules live)         ▲
                                                                          │ writes
                              ingestion workers (the ONLY net access) ────┘
                                   bulk CSV · report PDF postback chain · search
                                                  │
                                                  ▼
                                         guardian.ok.gov
```

- **Ingestion** (`guardian_contrib.ingest`) is the only code that touches
  Guardian. It downloads the bulk extract, walks the ASP.NET postback chain to
  fetch report PDFs, and parses the Schedule Summary.
- **Service layer** (`guardian_contrib.service`) applies the rules on read. The
  API and MCP are thin adapters over it, so they never diverge.
- **Store** (`guardian_contrib.models`) is SQLite locally / Postgres hosted —
  same SQLAlchemy schema.

## The two selection axes (categories)

| Axis A — who / where | Axis B — what |
|---|---|
| candidate · committee (Org ID) · district · office · party · cycle | summary · combined · continuing_total · contributions · loans · report · filing_history · flags |

A request = `{Axis A selector} × {Axis B category} × {window/options}`, available
as focused tools/endpoints or the single flexible `query`.

---

## Quickstart (local)

```bash
cd guardian-contributions-mcp
# NOTE: this path has spaces -> always prefix PYTHONPATH=src (uv's editable
# install silently breaks under spaced paths).

# tests (offline, penny-accurate against the known-good fixtures)
PYTHONPATH=src uv run --with pytest --with pytest-asyncio --with httpx pytest -q

# one-off ingestion (downloads the live ~1.8 MB extract; fetches roster PDFs)
PYTHONPATH=src uv run guardian-ingest            # add --no-reports for bulk only

# REST API  ->  http://localhost:8000/docs
PYTHONPATH=src uv run guardian-api

# MCP server (stdio)
PYTHONPATH=src uv run guardian-mcp

# build the Book(Sheet1) xlsx deliverable
PYTHONPATH=src uv run guardian-build-sheet --prior /path/to/previous.xlsx
```

### MCP host config (e.g. Claude Desktop / Claude Code)

```json
{
  "mcpServers": {
    "guardian-contributions": {
      "command": "uv",
      "args": ["run", "guardian-mcp"],
      "cwd": "/Users/cstillick/Desktop/Oklahoma State PAC Contributions/guardian-contributions-mcp",
      "env": { "PYTHONPATH": "src", "GUARDIAN_DATABASE_URL": "sqlite:///./guardian.db" }
    }
  }
}
```

---

## Deployment (hosted, multi-user)

```bash
cd deploy
GUARDIAN_API_KEYS=key-for-staff-1,key-for-staff-2 docker compose up -d --build
docker compose run --rm api guardian-ingest      # initial load
```

Brings up Postgres, the API (`:8000`, API-key auth), and the nightly scheduler
(refresh after Guardian's ~midnight rebuild, plus denser pulls around primary
day). Pass `X-API-Key: <key>` on every request.

---

## API surface (`/v1`)

| Endpoint | Category |
|---|---|
| `GET /candidates?name=&district=&office=&party=` | resolution (Axis A) |
| `GET /committees/{org_id}` · `/committees/{org_id}/filings` | committee / filings |
| `GET /reports/{filing_id}` | one report |
| `GET /committees/{org_id}/summary` | Pre-Primary figures |
| `GET /committees/{org_id}/continuing` | deduped continuing total |
| `GET /committees/{org_id}/combined` · `/districts/{d}/combined` | the headline number |
| `GET /contributions?org_id=&district=&from=&to=&type=&min_amount=` | itemized receipts |
| `GET /flags?district=&org_id=` | computed alerts |
| `GET /calendar?year=` · `GET /status` | windows · freshness |
| `POST /query` | flexible Axis A × Axis B selector |
| `POST /refresh` | trigger ingestion (background) |

MCP exposes the same as focused tools plus the `query` tool, and resources
`guardian://calendar/{year}`, `guardian://roster/{year}`, `guardian://status`.

---

## 14 Hard Rules → enforced invariants

| # | Rule | Where it's enforced |
|---|---|---|
| 1 | Windows computed, never hardcoded | `reporting_calendar` (3rd-Tue-of-June); `/calendar` |
| 2 | Continuing reports are incremental → dedup receipts | `compute.continuing` (dedup by Receipt ID) |
| 3 | Pre-Primary can't be rebuilt from bulk | `get_summary` only serves parsed-PDF figures |
| 4 | Report PDFs are retrievable | `guardian_client.fetch_report` (postback chain, sequential) |
| 5 | Match by Org ID, confirm district | `roster.resolve_org_id` (never fuzzy) + district check |
| 6 | One person, multiple committees | `committee_detail.is_regular_cycle` (`lblElection`) |
| 7 | Confirm year + committee | ingester rejects a report whose year ≠ cycle |
| 8 | Use the amended version | postback takes the **last** `lnkView` |
| 9 | Sub-$1,000 not on continuing reports | `flags.sub_threshold` |
| 10 | Data is a moving target | `as_of` on every response; scheduler |
| 11 | Version everything | runs append-only; builder archives, never overwrites |
| 12 | Full verification before delivery | `combined.identity_ok`; test suite |
| 13 | Freshness gate | `Run.changed_since_prev`; `/status` reports "no change" |
| 14 | Drop blank-Org-ID rows before dedup | `bulk.iter_receipts` |

---

## Tests

`pytest` (30+ tests) locks the invariants against the real data:

- combined balance identity holds for **all 77 rows** of the known-good sheet
- Roe reproduced to the penny three ways (synthetic, store, live PDF)
- bulk parser (embedded commas, malformed rows, blank Org IDs), PDF parser,
  continuing dedup/exclusions/split, flags, API endpoints, MCP tools, xlsx builder

Live end-to-end checks against `guardian.ok.gov` are opt-in:
`GUARDIAN_LIVE=1 PYTHONPATH=src uv run --with pytest pytest tests/test_live.py`.

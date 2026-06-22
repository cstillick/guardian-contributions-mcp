# Guardian Contributions — MCP + API

> ⚠️ **Archived — this is the original open-source prototype (`v0.1.0`, MIT).**
> Active development has moved to a maintained **commercial edition** with a hosted
> API + MCP, monitored data freshness (SLA), automated backups, and broader
> coverage. This repository is frozen at `v0.1.0` and will not receive updates.
> For a demo or licensing, contact **cooperstillick@icloud.com**.

A reusable service for **Oklahoma Ethics Commission "Guardian" campaign-finance
data**. It pulls and normalizes the data, then answers narrow questions through a
REST **API** and an **MCP** server (so Claude — or any MCP host — can use it as
tools).

It automates a workflow that's otherwise done by hand: for a roster of
candidates, combine each one's **Pre-Primary report** (Beginning, Raised, Loans,
Expended, Ending) with **all their Continuing contributions layered on top**, and
flag things like self-dealing loans. The business rules come from a manual
workflow distilled into 14 hard rules — each is enforced as a service invariant
([table below](#the-14-hard-rules--enforced-invariants)) and backed by a test.

**Status:** v0.1.0. 51 tests pass; the combined figures reproduce a known-good
deliverable **to the penny** (HD-42 Cynthia Roe: `$29,863.66 + $42,750.00 −
$4,278.24 = $68,335.42`), and an opt-in live test verifies the whole pipeline
against `guardian.ok.gov` end-to-end.

---

## Get started (about 2 minutes)

**Prerequisites:** Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`). No API key needed for local use.

```bash
git clone https://github.com/cstillick/guardian-contributions-mcp.git
cd guardian-contributions-mcp
uv sync                       # create the env + install the package

# 1) run the tests (offline; proves the rules against known-good fixtures)
uv run --extra dev pytest -q

# 2) load real data from Guardian
uv run guardian-ingest --no-reports     # fast: bulk contributions only (~5s)
#   or the full load (also fetches Pre-Primary report PDFs for the roster,
#   ~1–2 min because it walks Guardian's report pages one at a time):
# uv run guardian-ingest

# 3) start the server — web dashboard + REST API + interactive docs
uv run guardian-api           # dashboard: http://localhost:8000   ·   API docs: /docs
```

Then ask it things:

```bash
# the cycle's reporting calendar (computed, not hardcoded)
curl localhost:8000/v1/calendar

# one candidate's combined Pre-Primary + Continuing figures
curl "localhost:8000/v1/committees/11932/combined"
# -> {"beginning":"29863.66","raised":"42750.00","ending":"68335.42", ...}

# every candidate in a district
curl "localhost:8000/v1/districts/HD-42/combined"

# computed alerts (large loans, sub-$1,000 receipts, ...)
curl "localhost:8000/v1/flags?district=HD-42"
```

> `guardian-ingest` needs outbound access to `guardian.ok.gov`. Reads come
> entirely from the local database — Guardian is never touched on the request path.

---

## Web dashboard

`guardian-api` also serves a browsable **"Public Ledger"** UI at `/` — for people
who just want to open a link and read the numbers, no API knowledge needed:

- **`/`** — the roster as a sortable, filterable ledger (combined Beginning /
  Raised / Loan / Expended / Ending, flags, freshness dateline) plus **money-over-time**
  and **"who's raised the most"** charts.
- **`/c/{org_id}`** — a candidate dossier: the balance as an equation, the
  per-**reporting-period** balance chain (every Quarterly / Pre-Primary / Pre-General
  report via the layering model) with an **itemized vs unitemized** split, itemized
  contributions, filings, flags, and animated charts (**money over time**,
  **funding sources**, **top donors**).
- **`/flags`** — every computed alert across the roster, grouped by severity.
- **`/search`** — find any committee on file (candidates, PACs, parties) by name.

Editorial broadsheet design; server-rendered (Jinja2 + bespoke CSS), no build step.

---

## Use it from Claude (MCP)

Point any MCP host at the server. For Claude Desktop / Claude Code, add to your
MCP config:

```json
{
  "mcpServers": {
    "guardian-contributions": {
      "command": "uv",
      "args": ["run", "guardian-mcp"],
      "cwd": "/absolute/path/to/guardian-contributions-mcp"
    }
  }
}
```

Then ask in plain language — *"combined Pre-Primary + Continuing for HD-42 Cynthia
Roe,"* *"which candidates in HD-99 took loans larger than they raised?"* The model
picks from 13 focused tools plus a flexible `query` tool.

---

## What you're selecting between (the two axes)

A request = **who/where** × **what**:

| Axis A — who / where | Axis B — what |
|---|---|
| candidate · committee (Org ID) · district · office · party · cycle | summary · combined · continuing_total · contributions · loans · report · filing_history · flags |

## How it works

```
guardian.ok.gov ──▶ ingestion (bulk CSV + report-PDF postback chain) ──▶ store
                                                                           │
                              REST API  ◀── service layer (the 14 rules) ◀─┘
                              MCP tools  ◀──┘
```

Two halves hinged on the database: a **write path** (the only code that touches
Guardian — scrapes and normalizes on a schedule) and a **read path** (API + MCP,
serving fast from the store). Ingestion downloads one bulk extract for *all*
committees, then walks Guardian's ASP.NET report pages to fetch each Pre-Primary
PDF, parses the Schedule Summary, and stores it. Reads layer the stored
Pre-Primary figures on top of deduped continuing-window receipts.

### API surface (`/v1`, JSON, optional `X-API-Key`)

| Endpoint | Returns |
|---|---|
| `GET /candidates?name=&district=&office=&party=` | resolve candidates → committees |
| `GET /committees/{org_id}` · `/{org_id}/filings` · `/{org_id}/summary` | committee, filings, Pre-Primary figures |
| `GET /committees/{org_id}/continuing` · `/{org_id}/combined` | deduped continuing total · the headline number |
| `GET /districts/{d}/candidates` · `/districts/{d}/combined` | whole-race rollups |
| `GET /contributions?org_id=&district=&from=&to=&type=&min_amount=` | itemized receipts |
| `GET /reports/{filing_id}` · `/flags` · `/calendar` · `/status` | one report · alerts · windows · freshness |
| `POST /query` | flexible Axis A × Axis B selector |
| `POST /refresh` | trigger ingestion (background) |

Full interactive docs at `/docs` when the API is running.

---

## Deployment

**One always-on host (recommended)** — Postgres + API + nightly scheduler, no code changes:

```bash
cd deploy
GUARDIAN_API_KEYS=staff-key-1,staff-key-2 docker compose up -d --build
docker compose run --rm api guardian-ingest      # initial load
```

Set `GUARDIAN_DATABASE_URL` to a Postgres DSN for production (SQLite is the local
default — same schema). Pass `X-API-Key` on every request once keys are set.

**Serverless split (Vercel) —** the read API + web UI deploy fine to Vercel, but
the **ingestion is a long, stateful scrape** that doesn't fit serverless. The repo
ships a ready split: **Vercel** (UI + `/v1`) + a **GitHub Actions cron** (the
scraper) + **managed Postgres**. Files: `vercel.json`, `api/index.py`,
`requirements.txt`, `.github/workflows/ingest.yml`. Step-by-step in **[DEPLOY.md](DEPLOY.md)**.

---

## The 14 Hard Rules → enforced invariants

| # | Rule | Where it's enforced |
|---|---|---|
| 1 | Windows computed, never hardcoded | `reporting_calendar` (3rd-Tue-of-June); `/calendar` |
| 2 | Continuing reports are incremental → dedup receipts | `compute.continuing` (dedup by Receipt ID) |
| 3 | Pre-Primary can't be rebuilt from bulk | `get_summary` serves only parsed-PDF figures |
| 4 | Report PDFs are retrievable | `guardian_client.fetch_report` (postback chain, sequential) |
| 5 | Match by Org ID, confirm district | `roster.resolve_org_id` (never fuzzy) |
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

## Project layout

```
src/guardian_contrib/
  ingest/      bulk CSV + report-PDF postback chain + run orchestration
  compute/     continuing-sum · combined-layering · flags  (the rules)
  service.py   the one place rules are applied on read (API + MCP call this)
  api/         FastAPI app          mcp_server/  MCP server (stdio)
  builder/     Book(Sheet1) xlsx    scheduler.py nightly/election refresh
tests/         51 tests + fixtures (incl. opt-in live e2e: GUARDIAN_LIVE=1)
deploy/        Dockerfile + docker-compose (Postgres + API + scheduler)
```

## Troubleshooting

- **`guardian-ingest` hangs or errors:** confirm outbound access to
  `guardian.ok.gov`. Try `uv run guardian-ingest --no-reports` first (bulk only).
- **API returns empty/`null` data:** you haven't ingested yet — run
  `guardian-ingest`, then check `/v1/status` for the extract as-of date.
- **Imports fail in a checkout under a path with spaces:** prefix commands with
  `PYTHONPATH=src` (the editable install can be flaky there); a normal path needs nothing.

## License

MIT — see [LICENSE](LICENSE).

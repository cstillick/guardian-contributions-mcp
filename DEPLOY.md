# Deploying so other people can use it on the web

The service has two halves with very different needs, so they deploy to two places:

| Half | Where | Why |
|---|---|---|
| **Read API + web UI** | Vercel (serverless) | fast, scalable, cheap; what Vercel is built for |
| **Ingestion (the Guardian scrape)** | GitHub Actions cron | a long, stateful job — does NOT fit serverless time limits |

Both share one **managed Postgres**. The cron writes it nightly; Vercel reads it on
every request. (For a single always-on box instead, use `deploy/docker-compose.yml`
— it does everything in one place. This guide is the Vercel split.)

```
GitHub Actions cron ──(nightly scrape)──▶  Postgres  ◀──(reads)──  Vercel (UI + /v1 API)  ◀── users
```

## 1. Provision Postgres (Neon free tier works)

Create a database and grab two connection strings (Neon gives both):
- **Pooled** endpoint → for Vercel (serverless makes many short connections).
- **Direct** endpoint → for the ingest job (one long-lived writer).

Format them for SQLAlchemy + psycopg:
```
postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```
Tables are created automatically on first connect — no migration step.

## 2. Deploy the frontend + API to Vercel

1. Import the GitHub repo at [vercel.com/new](https://vercel.com/new). Vercel detects
   `api/index.py` (Python) and `vercel.json` rewrites every route to it.
2. Set **Environment Variables**:
   - `GUARDIAN_DATABASE_URL` = the **pooled** Postgres URL
   - `GUARDIAN_DEFAULT_CYCLE_YEAR` = `2026`
   - *(optional)* `GUARDIAN_API_KEYS` = `key1,key2` to require `X-API-Key` on `/v1`
     (the web UI stays public).
3. Deploy. Your URL serves the dashboard at `/`, the API at `/v1`, docs at `/docs`.

> `requirements.txt` is the lean read-only dependency set for the function — it
> excludes the scraping/PDF/MCP libraries so the bundle stays small. `/v1/refresh`
> is a no-op here; the cron does ingestion.

## 3. Schedule the scraper (GitHub Actions)

The workflow `.github/workflows/ingest.yml` is already in the repo. Just:

1. Repo → **Settings → Secrets and variables → Actions** → add
   `GUARDIAN_DATABASE_URL` = the **direct** Postgres URL.
2. Repo → **Actions → nightly-ingest → Run workflow** to do the **initial load**
   now (don't wait for the first nightly).

It then runs nightly at 06:30 UTC (after Oklahoma's ~midnight extract rebuild),
with extra pulls around primary day. Each run does the full bulk + report scrape on
GitHub's runner and writes Postgres.

## 4. Done

Share the Vercel URL. Visitors see current figures; freshness updates whenever the
cron runs (the dateline shows the extract as-of date). To refresh on demand, trigger
the workflow manually.

### Notes
- **Connection pooling matters:** use Neon's *pooled* string on Vercel, the *direct*
  string for the cron. Skipping the pooler on serverless leads to connection storms.
- **Scope:** ingestion reads every committee; the dashboard is roster-scoped
  (`ROSTER_2026` in `src/guardian_contrib/roster.py`) — edit it to cover more races.
- **MCP** isn't part of this deploy (it's stdio; run it locally, or host the
  Streamable-HTTP transport on an always-on box).

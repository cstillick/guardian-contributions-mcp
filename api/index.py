"""Vercel serverless entry point — serves the read API + Public Ledger web UI as
one ASGI app, reading from a managed Postgres.

Ingestion does NOT run here: the long Guardian scrape doesn't fit serverless time
limits, so a separate GitHub Actions cron loads Postgres (.github/workflows/
ingest.yml). The /v1/refresh endpoint is therefore a no-op on this deploy.
See DEPLOY.md.
"""
import pathlib
import sys

# src layout: make the package importable without an install step.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from guardian_contrib.api.app import app  # noqa: E402  (Vercel detects `app`)

__all__ = ["app"]

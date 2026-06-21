"""Every module imports cleanly (catches missing deps / syntax across the package,
including modules the other tests don't exercise — scheduler, api.app, builder)."""
import importlib

import pytest

MODULES = [
    "config", "db", "models", "money", "reporting_calendar", "roster", "service",
    "scheduler",
    "ingest.bulk", "ingest.reports", "ingest.guardian_client", "ingest.runner",
    "compute.continuing", "compute.combined", "compute.flags",
    "api.app", "mcp_server.server", "builder.xlsx",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(f"guardian_contrib.{mod}")

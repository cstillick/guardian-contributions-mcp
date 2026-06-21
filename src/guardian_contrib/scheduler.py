"""Scheduled ingestion (Rule 10): nightly refresh after Guardian's ~midnight
rebuild, with an optional denser cadence around election day.

Run as a long-lived process (own container in the hosted deployment):
    guardian-schedule
Env:
    GUARDIAN_REFRESH_CRON_HOUR   (default 1)   nightly hour, local time
    GUARDIAN_REFRESH_CRON_MINUTE (default 30)
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .ingest.runner import ingest_run

log = logging.getLogger("guardian.scheduler")


def _refresh() -> None:
    settings = get_settings()
    log.info("scheduled refresh starting (year=%s)", settings.default_cycle_year)
    try:
        result = ingest_run(year=settings.default_cycle_year, enrich_roster=True)
        log.info("refresh done: run_id=%s changed=%s enriched=%s",
                 result.get("run_id"), result.get("changed_since_prev"), result.get("enriched"))
    except Exception:
        log.exception("scheduled refresh failed")


def build_scheduler() -> BlockingScheduler:
    hour = int(os.environ.get("GUARDIAN_REFRESH_CRON_HOUR", "1"))
    minute = int(os.environ.get("GUARDIAN_REFRESH_CRON_MINUTE", "30"))
    sched = BlockingScheduler()
    # Nightly full refresh.
    sched.add_job(_refresh, CronTrigger(hour=hour, minute=minute), id="nightly",
                  replace_existing=True)
    # Election-night / primary-day extra pulls (continuing reports arrive late).
    sched.add_job(_refresh, CronTrigger(month=6, day="16-18", hour="6,12,20"),
                  id="election_window", replace_existing=True)
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sched = build_scheduler()
    log.info("scheduler started; jobs: %s", [j.id for j in sched.get_jobs()])
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")


if __name__ == "__main__":
    main()

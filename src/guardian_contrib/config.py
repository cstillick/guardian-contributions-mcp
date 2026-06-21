"""Runtime configuration (env-driven, 12-factor).

SQLite by default for local dev/tests; set DATABASE_URL to a Postgres DSN for the
hosted deployment. Same schema either way.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUARDIAN_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "sqlite:///./guardian.db"

    # Guardian source
    guardian_base: str = "https://guardian.ok.gov/PublicSite"
    bulk_url_template: str = (
        "https://guardian.ok.gov/PublicSite/Docs/BulkDataDownloads/"
        "{year}_ContributionLoanExtract.csv.zip"
    )
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) guardian-contrib/0.1"
    )
    request_timeout: float = 90.0

    # Cycle
    default_cycle_year: int = 2026

    # Auth — comma-separated API keys; empty list disables auth (local single-user).
    # NoDecode: take the raw env string and split it ourselves (not JSON).
    api_keys: Annotated[list[str], NoDecode] = []

    # Filesystem
    pdf_cache_dir: Path = Path("./data/pdf_cache")
    output_dir: Path = Path("./data/output")
    roster_path: Path | None = None

    @field_validator("api_keys", mode="before")
    @classmethod
    def _split_keys(cls, v):
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    def bulk_url(self, year: int | None = None) -> str:
        return self.bulk_url_template.format(year=year or self.default_cycle_year)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

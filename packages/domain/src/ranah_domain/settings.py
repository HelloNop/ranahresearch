"""Typed configuration. No secrets in the repository; values come from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DomainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    database_url: str = "postgresql+psycopg://ranah:ranah-local-only@127.0.0.1:5432/ranahresearch"
    database_echo: bool = False


@lru_cache
def get_settings() -> DomainSettings:
    return DomainSettings()

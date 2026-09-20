"""Typed configuration. No secrets in the repository; values come from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DomainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    database_url: str = "postgresql+psycopg://ranah:ranah-local-only@127.0.0.1:5432/ranahresearch"
    database_echo: bool = False
    s3_endpoint_url: str = "http://127.0.0.1:9002"
    s3_region: str = "us-east-1"
    s3_bucket: str = "ranahresearch"
    s3_access_key_id: str = "ranah-local"
    s3_secret_access_key: str = "ranah-local-secret"


@lru_cache
def get_settings() -> DomainSettings:
    return DomainSettings()

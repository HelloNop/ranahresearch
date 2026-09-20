"""Temporal client bootstrap. Typed configuration, no secrets in the repository."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from temporalio.client import Client


class TemporalSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"


async def connect_client(settings: TemporalSettings | None = None) -> Client:
    settings = settings or TemporalSettings()
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)

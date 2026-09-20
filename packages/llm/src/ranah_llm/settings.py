"""Typed configuration for wiring a real OpenAIProvider. No secrets in the repository."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAISettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

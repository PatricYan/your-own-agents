"""Model configuration and registry for managing model providers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelStatus(StrEnum):
    """Status of a registered model configuration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class ModelConfig(BaseModel):
    """A registered model provider configuration."""

    name: str
    provider: str
    connection: dict[str, Any]
    capabilities: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: ModelStatus = ModelStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Model name must be non-empty")
        return v.strip()

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Provider must be non-empty")
        return v.strip().lower()

    @field_validator("connection")
    @classmethod
    def validate_connection(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("Connection details must be provided")
        return v


class ModelRegistry:
    """In-memory registry for model configurations."""

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}

    def register(self, config: ModelConfig) -> None:
        if config.name in self._models:
            raise ValueError(f"Model '{config.name}' is already registered")
        self._models[config.name] = config

    def get(self, name: str) -> ModelConfig:
        if name not in self._models:
            raise KeyError(f"Model '{name}' not found")
        return self._models[name]

    def list_models(self, provider: str | None = None) -> list[ModelConfig]:
        models = list(self._models.values())
        if provider:
            models = [m for m in models if m.provider == provider.lower()]
        return models

    def remove(self, name: str) -> None:
        if name not in self._models:
            raise KeyError(f"Model '{name}' not found")
        del self._models[name]

    def has(self, name: str) -> bool:
        return name in self._models


def load_models_from_file(path: str | Path) -> list[ModelConfig]:
    """Load model configurations from a YAML file.

    File format::

        models:
          - name: gpt-4o
            provider: openai
            connection:
              api_key_env: OPENAI_API_KEY
              model: gpt-4o
          - name: claude
            provider: anthropic
            connection:
              api_key_env: ANTHROPIC_API_KEY
              model: claude-sonnet-4-20250514
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Models config file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "models" not in raw:
        raise ValueError(f"Models config must have a 'models' key: {path}")

    configs = []
    for entry in raw["models"]:
        configs.append(ModelConfig(**entry))
    return configs


def load_models_from_list(raw_models: list[dict[str, Any]]) -> list[ModelConfig]:
    """Load model configurations from a list of dicts (inline in pipeline YAML)."""
    configs = []
    for entry in raw_models:
        configs.append(ModelConfig(**entry))
    return configs

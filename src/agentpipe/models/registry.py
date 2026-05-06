"""Model configuration — load from YAML files or dicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelConfig(BaseModel):
    """A model provider configuration.

    Defined in YAML (models.yaml or inline in pipeline YAML)::

        models:
          - name: gpt-4o
            provider: openai
            connection:
              api_key: OPENAI_API_KEY
              model: gpt-4o
    """

    name: str
    provider: str
    connection: dict[str, Any]
    capabilities: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)

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


def load_models_from_file(path: str | Path) -> list[ModelConfig]:
    """Load model configurations from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Models config file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "models" not in raw:
        raise ValueError(f"Models config must have a 'models' key: {path}")

    return [ModelConfig(**entry) for entry in raw["models"]]


def load_models_from_list(raw_models: list[dict[str, Any]]) -> list[ModelConfig]:
    """Load model configurations from a list of dicts."""
    return [ModelConfig(**entry) for entry in raw_models]

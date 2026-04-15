"""Model configuration and registry for managing model providers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

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
    """In-memory registry for model configurations with file-backed persistence."""

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}

    def register(self, config: ModelConfig) -> None:
        """Register a model configuration."""
        if config.name in self._models:
            raise ValueError(f"Model '{config.name}' is already registered")
        self._models[config.name] = config

    def get(self, name: str) -> ModelConfig:
        """Get a model configuration by name."""
        if name not in self._models:
            raise KeyError(f"Model '{name}' not found")
        return self._models[name]

    def list_models(self, provider: str | None = None) -> list[ModelConfig]:
        """List all registered models, optionally filtered by provider."""
        models = list(self._models.values())
        if provider:
            models = [m for m in models if m.provider == provider.lower()]
        return models

    def remove(self, name: str) -> None:
        """Remove a model configuration."""
        if name not in self._models:
            raise KeyError(f"Model '{name}' not found")
        del self._models[name]

    def has(self, name: str) -> bool:
        """Check if a model is registered."""
        return name in self._models

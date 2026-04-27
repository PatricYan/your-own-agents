"""Model adapter factory. All values from config, nothing hardcoded."""

from __future__ import annotations

from agentpipe.models.provider import ModelProvider
from agentpipe.models.registry import ModelConfig


def create_provider(config: ModelConfig) -> ModelProvider:
    """Create a ModelProvider from a ModelConfig.

    connection must have: api_key (env var name), base_url, model
    """
    provider = config.provider.lower()
    conn = config.connection

    if provider in ("openai", "microsoft-foundry-openai"):
        from agentpipe.models.adapters.openai import OpenAIModelProvider

        return OpenAIModelProvider(
            api_key=conn["api_key"],
            base_url=conn["base_url"],
            model=conn.get("model", ""),
            default_params=config.parameters,
        )

    if provider in ("anthropic", "microsoft-foundry-anthropic"):
        from agentpipe.models.adapters.anthropic import AnthropicModelProvider

        return AnthropicModelProvider(
            api_key=conn["api_key"],
            base_url=conn["base_url"],
            model=conn.get("model", ""),
            default_params=config.parameters,
        )

    if provider == "ollama":
        from agentpipe.models.adapters.ollama import OllamaModelProvider

        return OllamaModelProvider(
            base_url=conn["base_url"],
            model=conn.get("model", ""),
            default_params=config.parameters,
        )

    if provider == "http":
        from agentpipe.models.adapters.http import HttpModelProvider

        return HttpModelProvider(
            base_url=conn["base_url"],
            model=conn.get("model"),
            headers=conn.get("headers"),
            timeout=conn.get("timeout", 60.0),
        )

    raise ValueError(
        f"Unknown provider: '{provider}'. "
        f"Supported: openai, anthropic, microsoft-foundry-anthropic, "
        f"microsoft-foundry-openai, ollama, http"
    )

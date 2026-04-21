"""Model adapter factory and auto-discovery."""

from __future__ import annotations

from agentpipe.models.provider import ModelProvider
from agentpipe.models.registry import ModelConfig


def create_provider(config: ModelConfig) -> ModelProvider:
    """Create a ModelProvider instance from a ModelConfig.

    Dispatches to the appropriate adapter based on the provider field.

    Args:
        config: The model configuration.

    Returns:
        An instantiated ModelProvider.

    Raises:
        ValueError: If the provider type is not recognized.
    """
    provider = config.provider.lower()

    if provider == "http":
        from agentpipe.models.adapters.http import HttpModelProvider

        return HttpModelProvider(
            base_url=config.connection.get("base_url", ""),
            model=config.connection.get("model"),
            headers=config.connection.get("headers"),
            timeout=config.connection.get("timeout", 60.0),
        )
    elif provider == "openai":
        from agentpipe.models.adapters.openai import OpenAIModelProvider

        return OpenAIModelProvider(
            api_key_env=config.connection.get("api_key_env", "OPENAI_API_KEY"),
            base_url=config.connection.get("base_url", "https://api.openai.com/v1"),
            model=config.connection.get("model", "gpt-4o"),
            default_params=config.parameters,
        )
    elif provider == "anthropic":
        from agentpipe.models.adapters.anthropic import AnthropicModelProvider

        return AnthropicModelProvider(
            api_key_env=config.connection.get("api_key_env", "ANTHROPIC_API_KEY"),
            base_url=config.connection.get("base_url", "https://api.anthropic.com"),
            model=config.connection.get("model", "claude-sonnet-4-20250514"),
            default_params=config.parameters,
        )
    elif provider == "ollama":
        from agentpipe.models.adapters.ollama import OllamaModelProvider

        return OllamaModelProvider(
            base_url=config.connection.get("base_url"),  # falls back to OLLAMA_BASE_URL env var
            model=config.connection.get("model", "llama3"),
            default_params=config.parameters,
        )
    else:
        raise ValueError(
            f"Unknown provider type: '{provider}'. Supported: openai, anthropic, ollama, http"
        )

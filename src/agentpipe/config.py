"""Central configuration — reads from environment variables.

All defaults are defined here. No other file should hardcode
port numbers, hostnames, or URLs.

Configuration priority: env var > default value here.
"""

from __future__ import annotations

import os


def get(key: str, default: str = "") -> str:
    """Read a config value from the environment."""
    return os.environ.get(key, default)


# === Backend ===
HOST = get("AGENTPIPE_HOST", "0.0.0.0")
PORT = int(get("AGENTPIPE_PORT", "8420"))
LOG_LEVEL = get("AGENTPIPE_LOG_LEVEL", "info")

# === Ollama ===
OLLAMA_BASE_URL = get("OLLAMA_BASE_URL", "http://localhost:11434")

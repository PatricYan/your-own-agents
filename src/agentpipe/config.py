"""Central configuration — loads .env automatically, reads from environment variables."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# === Backend ===
HOST = get("AGENTPIPE_HOST", "0.0.0.0")
PORT = int(get("AGENTPIPE_PORT", "8420"))
LOG_LEVEL = get("AGENTPIPE_LOG_LEVEL", "info")

# === Pipelines ===
PIPELINES_DIR = get("AGENTPIPE_PIPELINES_DIR", "examples")

# === Models ===
MODELS_FILE = get("AGENTPIPE_MODELS", "")

# === Agent Rules ===
RULES_FILE = get("AGENTPIPE_RULES", "")

# === Logs ===
LOGS_DIR = get("AGENTPIPE_LOGS_DIR", "")

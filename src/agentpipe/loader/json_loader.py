"""JSON pipeline definition loader."""

from __future__ import annotations

import json
from pathlib import Path

from agentpipe.core.pipeline import Pipeline
from agentpipe.loader.yaml_loader import load_pipeline_from_dict


def load_pipeline_from_json(path: str | Path) -> Pipeline:
    """Load a pipeline definition from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        A validated Pipeline instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is invalid or missing required fields.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {path}")

    raw = json.loads(path.read_text())
    return load_pipeline_from_dict(raw)


def load_pipeline_from_json_string(content: str) -> Pipeline:
    """Load a pipeline definition from a JSON string."""
    raw = json.loads(content)
    return load_pipeline_from_dict(raw)

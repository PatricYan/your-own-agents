"""Start the API server."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def cmd_serve(args, workspace: Path, fmt: str) -> int:
    try:
        import uvicorn
    except ImportError:
        print("Error: Run: pip install agentpipe[web]", file=sys.stderr)
        return 1

    from agentpipe import config
    from agentpipe.web.api import create_app

    # Set up logging so API task logs appear on console
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    host = getattr(args, "host", None) or config.HOST
    port = getattr(args, "port", None) or config.PORT

    app = create_app(workspace=str(workspace))

    print("AgentPipe API server")
    print(f"  Host:       {host}:{port}")
    print(f"  Pipelines:  {config.PIPELINES_DIR}")
    if config.MODELS_FILE:
        print(f"  Models:     {config.MODELS_FILE}")
    if config.LOGS_DIR:
        print(f"  Logs:       {config.LOGS_DIR}")
    print(f"  API:        http://{host}:{port}/api/pipelines")
    print()

    uvicorn.run(app, host=host, port=port, log_level=config.LOG_LEVEL)
    return 0

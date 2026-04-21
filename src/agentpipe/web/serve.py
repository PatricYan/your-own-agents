"""Start the API server. Configuration from agentpipe.config (env vars)."""

from __future__ import annotations

import sys
from pathlib import Path


def cmd_serve(args, workspace: Path, fmt: str) -> int:
    """Start the API server."""
    try:
        import uvicorn
    except ImportError:
        print(
            "Error: Web server dependencies not installed.\n"
            "Install with: pip install agentpipe[web]",
            file=sys.stderr,
        )
        return 1

    from agentpipe import config
    from agentpipe.web.api import create_app

    # CLI flags override config (which reads from env vars)
    host = getattr(args, "host", None) or config.HOST
    port = getattr(args, "port", None) or config.PORT
    log_level = config.LOG_LEVEL

    app = create_app(workspace=str(workspace))

    print("AgentPipe API server")
    print(f"  Host:      {host}:{port}")
    print(f"  API:       http://{host}:{port}/api/pipelines")
    print(f"  WebSocket: ws://{host}:{port}/ws")
    print(f"  Workspace: {workspace}")
    print()

    uvicorn.run(app, host=host, port=port, log_level=log_level)
    return 0

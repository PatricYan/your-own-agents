"""CLI handler for 'agentpipe serve' — starts the web UI and API server."""

from __future__ import annotations

import sys
from pathlib import Path


def cmd_serve(args, workspace: Path, fmt: str) -> int:
    """Start the web server."""
    try:
        import uvicorn
    except ImportError:
        print(
            "Error: Web server dependencies not installed.\n"
            "Install with: pip install agentpipe[web]",
            file=sys.stderr,
        )
        return 1

    from agentpipe.web.api import create_app

    host = getattr(args, "host", "0.0.0.0")
    port = getattr(args, "port", 8420)
    static_dir = getattr(args, "static_dir", None)

    # Try to find the React build
    if static_dir is None:
        candidates = [
            Path(__file__).parent.parent.parent.parent / "web" / "frontend" / "build",
            workspace / "web" / "frontend" / "build",
        ]
        for c in candidates:
            if c.exists():
                static_dir = str(c)
                break

    app = create_app(workspace=str(workspace), static_dir=static_dir)

    print(f"AgentPipe server starting on http://{host}:{port}")
    print(f"  API:       http://{host}:{port}/api/pipelines")
    print(f"  WebSocket: ws://{host}:{port}/ws")
    if static_dir:
        print(f"  UI:        http://{host}:{port}/")
    else:
        print("  UI:        Not built. Run: cd web/frontend && npm run build")
    print(f"  Workspace: {workspace}")
    print()

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0

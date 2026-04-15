"""CLI 'status' command handler: query execution status and history."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def cmd_status(args, workspace: Path, fmt: str) -> int:
    """Dispatch status subcommands."""
    cmd = args.status_command
    if cmd == "show":
        return _status_show(args, workspace, fmt)
    elif cmd == "list":
        return _status_list(args, workspace, fmt)
    else:
        print("Usage: agentpipe status {show|list}", file=sys.stderr)
        return 1


def _status_show(args, workspace: Path, fmt: str) -> int:
    """Show details of a specific execution run."""
    from agentpipe.storage.history import HistoryStore

    store = HistoryStore(workspace)

    run = store.get_run(args.run_id)
    if run is None:
        from agentpipe.cli.main import ErrorCode, error_output

        error_output(ErrorCode.AGENT_NOT_FOUND, f"Run '{args.run_id}' not found", fmt=fmt)
        return 2

    if fmt == "json":
        print(json.dumps(run, indent=2, default=str))
    else:
        print(f"Run ID: {run['id']}")
        print(f"Pipeline: {run.get('pipeline_name', 'N/A')}")
        print(f"Status: {run.get('status', 'N/A')}")
        print(f"Started: {run.get('started_at', 'N/A')}")
        print(f"Completed: {run.get('completed_at', 'N/A')}")
        if run.get("error"):
            print(f"Error: {run['error']}")
        tasks = run.get("task_executions", [])
        if tasks:
            print(f"\nTasks ({len(tasks)}):")
            for t in tasks:
                status = t.get("status", "?")
                duration = t.get("duration_ms", 0)
                model = t.get("model_used", "N/A")
                retries = t.get("retry_count", 0)
                print(
                    f"  {t.get('task_name', '?')}: {status} ({duration}ms, model: {model}, retries: {retries})"
                )
                if t.get("error"):
                    print(f"    Error: {t['error']}")

    return 0


def _status_list(args, workspace: Path, fmt: str) -> int:
    """List recent execution runs."""
    from agentpipe.storage.history import HistoryStore

    store = HistoryStore(workspace)

    agent_name = getattr(args, "agent_name", None)
    limit = getattr(args, "limit", 20)
    status_filter = getattr(args, "status", None)

    runs = store.list_runs(agent_name=agent_name, limit=limit, status=status_filter)

    if fmt == "json":
        print(json.dumps({"runs": runs}, indent=2, default=str))
    else:
        if not runs:
            print("No execution runs found.")
        else:
            print("Recent runs:")
            for run in runs:
                status = run.get("status", "?")
                pipeline = run.get("pipeline_name", "?")
                started = run.get("started_at", "?")
                print(f"  {run.get('id', '?')[:12]}... | {pipeline} | {status} | {started}")

    return 0

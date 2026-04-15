"""CLI main entry point with command dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentpipe import __version__


# Error codes per cli-contract.md
class ErrorCode:
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    PIPELINE_INVALID = "PIPELINE_INVALID"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    CONSTRAINT_VIOLATED = "CONSTRAINT_VIOLATED"
    INPUT_INVALID = "INPUT_INVALID"
    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"
    RECOVERY_EXHAUSTED = "RECOVERY_EXHAUSTED"


def error_output(code: str, message: str, details: dict | None = None, fmt: str = "text") -> None:
    """Write structured error output to stderr."""
    if fmt == "json":
        err = {"error": {"code": code, "message": message, "details": details or {}}}
        print(json.dumps(err), file=sys.stderr)
    else:
        print(f"Error [{code}]: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentpipe",
        description="AgentPipe: An Airflow-inspired pipeline framework for AI agents",
    )
    parser.add_argument("--version", action="version", version=f"agentpipe {__version__}")
    parser.add_argument(
        "-f", "--format", choices=["text", "json"], default="text", help="Output format"
    )
    parser.add_argument("-w", "--workspace", type=str, default=".", help="Workspace directory path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- run command ---
    run_parser = subparsers.add_parser("run", help="Execute an agent's pipeline")
    run_parser.add_argument("agent_name", help="Name of the agent to execute")
    run_parser.add_argument("--input", dest="input_data", help="JSON string of initial input")
    run_parser.add_argument("--input-file", help="Path to JSON/YAML input file")
    run_parser.add_argument("--watch", action="store_true", help="Stream execution status")
    run_parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode: Ctrl+C to pause, modify permissions/goal/prompt, then resume",
    )
    run_parser.add_argument("--timeout", type=float, help="Execution timeout in seconds")

    # --- agents command ---
    agents_parser = subparsers.add_parser("agents", help="Manage agent definitions")
    agents_sub = agents_parser.add_subparsers(dest="agents_command")

    agents_create = agents_sub.add_parser("create", help="Create a new agent")
    agents_create.add_argument("name", help="Agent name")
    agents_create.add_argument("--pipeline", required=True, help="Pipeline definition file path")
    agents_create.add_argument("--description", help="Agent description")

    agents_sub.add_parser("list", help="List all agents")

    agents_inspect = agents_sub.add_parser("inspect", help="Inspect agent details")
    agents_inspect.add_argument("name", help="Agent name")

    agents_delete = agents_sub.add_parser("delete", help="Delete an agent")
    agents_delete.add_argument("name", help="Agent name")
    agents_delete.add_argument("--force", action="store_true", help="Skip confirmation")

    # --- models command ---
    models_parser = subparsers.add_parser("models", help="Manage model configurations")
    models_sub = models_parser.add_subparsers(dest="models_command")

    models_register = models_sub.add_parser("register", help="Register a model")
    models_register.add_argument("name", help="Model name")
    models_register.add_argument("--provider", required=True, help="Provider type")
    models_register.add_argument("--connection", required=True, help="Connection JSON or file")
    models_register.add_argument("--capabilities", help="Comma-separated capabilities")
    models_register.add_argument("--parameters", help="Default parameters JSON")

    models_list = models_sub.add_parser("list", help="List registered models")
    models_list.add_argument("--provider", help="Filter by provider")

    models_test = models_sub.add_parser("test", help="Test a model")
    models_test.add_argument("name", help="Model name")
    models_test.add_argument(
        "--prompt", default="Hello, please respond briefly.", help="Test prompt"
    )

    models_remove = models_sub.add_parser("remove", help="Remove a model")
    models_remove.add_argument("name", help="Model name")
    models_remove.add_argument("--force", action="store_true", help="Skip confirmation")

    # --- pipelines command ---
    pipelines_parser = subparsers.add_parser("pipelines", help="Manage pipeline definitions")
    pipelines_sub = pipelines_parser.add_subparsers(dest="pipelines_command")

    pipelines_validate = pipelines_sub.add_parser("validate", help="Validate a pipeline file")
    pipelines_validate.add_argument("path", help="Pipeline definition file path")

    pipelines_dag = pipelines_sub.add_parser("dag", help="View pipeline DAG (like Airflow)")
    pipelines_dag.add_argument("path", help="Pipeline definition file path")
    pipelines_dag.add_argument(
        "--mermaid",
        action="store_true",
        help="Output as Mermaid diagram (for GitHub, Notion, mermaid.live)",
    )

    pipelines_inspect = pipelines_sub.add_parser("inspect", help="Inspect pipeline structure")
    pipelines_inspect.add_argument("agent_name", help="Agent name")

    # --- status command ---
    status_parser = subparsers.add_parser("status", help="Query execution status")
    status_sub = status_parser.add_subparsers(dest="status_command")

    status_show = status_sub.add_parser("show", help="Show run details")
    status_show.add_argument("run_id", help="Execution run ID")

    status_list = status_sub.add_parser("list", help="List recent runs")
    status_list.add_argument("agent_name", nargs="?", help="Filter by agent name")
    status_list.add_argument("--limit", type=int, default=20, help="Max runs to show")
    status_list.add_argument("--status", help="Filter by status")

    # --- serve command ---
    serve_parser = subparsers.add_parser(
        "serve", help="Start the web UI and API server (like Airflow/n8n)"
    )
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8420, help="Bind port (default: 8420)")
    serve_parser.add_argument(
        "--static-dir", dest="static_dir", help="Path to React build directory"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    import logging

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    fmt = args.format
    workspace = Path(args.workspace).resolve()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "run":
            from agentpipe.cli.run import cmd_run

            return cmd_run(args, workspace, fmt)

        elif args.command == "agents":
            from agentpipe.cli.pipelines import cmd_agents

            return cmd_agents(args, workspace, fmt)

        elif args.command == "models":
            from agentpipe.cli.models import cmd_models

            return cmd_models(args, workspace, fmt)

        elif args.command == "pipelines":
            from agentpipe.cli.pipelines import cmd_pipelines

            return cmd_pipelines(args, workspace, fmt)

        elif args.command == "status":
            from agentpipe.cli.status import cmd_status

            return cmd_status(args, workspace, fmt)

        elif args.command == "serve":
            from agentpipe.web.serve import cmd_serve

            return cmd_serve(args, workspace, fmt)

        else:
            parser.print_help()
            return 0

    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        error_output("INTERNAL_ERROR", str(e), fmt=fmt)
        return 1


if __name__ == "__main__":
    sys.exit(main())

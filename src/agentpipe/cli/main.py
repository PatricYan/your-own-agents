"""CLI — all inputs are files, no inline strings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentpipe import __version__


class ErrorCode:
    PIPELINE_INVALID = "PIPELINE_INVALID"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    INPUT_INVALID = "INPUT_INVALID"
    RECOVERY_EXHAUSTED = "RECOVERY_EXHAUSTED"


def error_output(code: str, message: str, details: dict | None = None, fmt: str = "text") -> None:
    if fmt == "json":
        print(json.dumps({"error": {"code": code, "message": message}}), file=sys.stderr)
    else:
        print(f"Error [{code}]: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentpipe",
        description="AgentPipe — build your own agent pipelines",
    )
    parser.add_argument("--version", action="version", version=f"agentpipe {__version__}")
    parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
    parser.add_argument("-w", "--workspace", type=str, default=".")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command")

    # agentpipe run <pipeline.yaml> [--watch] [-i]
    run_p = sub.add_parser("run", help="Run a pipeline YAML file")
    run_p.add_argument("pipeline", help="Pipeline YAML file")
    run_p.add_argument("--watch", action="store_true", help="Stream execution status")
    run_p.add_argument("-i", "--interactive", action="store_true", help="Pause/modify/resume")

    # agentpipe validate <pipeline.yaml>
    sub.add_parser("validate", help="Validate a pipeline file").add_argument("path")

    # agentpipe dag <pipeline.yaml> [--mermaid]
    dag_p = sub.add_parser("dag", help="View pipeline DAG")
    dag_p.add_argument("path", help="Pipeline YAML file")
    dag_p.add_argument("--mermaid", action="store_true")

    # agentpipe serve
    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", default=None, help="env: AGENTPIPE_HOST")
    serve_p.add_argument("--port", type=int, default=None, help="env: AGENTPIPE_PORT")

    return parser


def main(argv: list[str] | None = None) -> int:
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

        if args.command in ("validate", "dag"):
            from agentpipe.cli.pipelines import cmd_dag, cmd_validate

            if args.command == "validate":
                return cmd_validate(args, workspace, fmt)
            return cmd_dag(args, workspace, fmt)

        if args.command == "serve":
            from agentpipe.web.serve import cmd_serve

            return cmd_serve(args, workspace, fmt)

        parser.print_help()
        return 0

    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        error_output("INTERNAL_ERROR", str(e), fmt=fmt)
        return 1


if __name__ == "__main__":
    sys.exit(main())

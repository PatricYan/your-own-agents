"""CLI 'models' command handler: register, list, test, and remove models."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from agentpipe.cli.main import ErrorCode, error_output


def cmd_models(args, workspace: Path, fmt: str) -> int:
    """Dispatch models subcommands."""
    cmd = args.models_command
    if cmd == "register":
        return _models_register(args, workspace, fmt)
    elif cmd == "list":
        return _models_list(args, workspace, fmt)
    elif cmd == "test":
        return _models_test(args, workspace, fmt)
    elif cmd == "remove":
        return _models_remove(args, workspace, fmt)
    else:
        print("Usage: agentpipe models {register|list|test|remove}", file=sys.stderr)
        return 1


def _models_register(args, workspace: Path, fmt: str) -> int:
    """Register a new model configuration."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)

    # Parse connection config
    connection = _parse_connection(args.connection)
    if connection is None:
        error_output(ErrorCode.INPUT_INVALID, "Cannot parse connection config as JSON", fmt=fmt)
        return 3

    # Parse capabilities
    capabilities = []
    if args.capabilities:
        capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]

    # Parse parameters
    parameters = {}
    if args.parameters:
        try:
            parameters = json.loads(args.parameters)
        except json.JSONDecodeError:
            error_output(ErrorCode.INPUT_INVALID, "Cannot parse parameters as JSON", fmt=fmt)
            return 3

    # Check if model already exists
    if args.name in store.list_models():
        error_output(ErrorCode.PIPELINE_INVALID, f"Model '{args.name}' already exists", fmt=fmt)
        return 1

    model_data = {
        "name": args.name,
        "provider": args.provider,
        "connection": connection,
        "capabilities": capabilities,
        "parameters": parameters,
        "status": "active",
    }

    store.save_model(args.name, model_data)

    if fmt == "json":
        print(json.dumps({"status": "registered", "name": args.name}))
    else:
        print(f"Model '{args.name}' registered successfully.")
        print(f"  Provider: {args.provider}")
        if capabilities:
            print(f"  Capabilities: {', '.join(capabilities)}")

    return 0


def _models_list(args, workspace: Path, fmt: str) -> int:
    """List all registered models."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)
    model_names = store.list_models()

    if args.provider:
        # Filter by loading and checking provider
        filtered = []
        for name in model_names:
            data = store.load_model(name)
            if data.get("provider", "").lower() == args.provider.lower():
                filtered.append(name)
        model_names = filtered

    if fmt == "json":
        models = []
        for name in model_names:
            data = store.load_model(name)
            models.append(data)
        print(json.dumps({"models": models}, indent=2, default=str))
    else:
        if not model_names:
            print("No models registered.")
        else:
            print("Models:")
            for name in model_names:
                data = store.load_model(name)
                status = data.get("status", "unknown")
                provider = data.get("provider", "unknown")
                caps = ", ".join(data.get("capabilities", [])) or "none"
                print(f"  - {name} ({provider}) [{status}] capabilities: {caps}")

    return 0


def _models_test(args, workspace: Path, fmt: str) -> int:
    """Test a model configuration by sending a simple prompt."""
    from agentpipe.models.adapters import create_provider
    from agentpipe.models.registry import ModelConfig
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)

    try:
        data = store.load_model(args.name)
    except FileNotFoundError:
        error_output(ErrorCode.MODEL_NOT_FOUND, f"Model '{args.name}' not found", fmt=fmt)
        return 2

    config = ModelConfig(**data)

    try:
        provider = create_provider(config)
    except Exception as e:
        error_output(ErrorCode.MODEL_UNAVAILABLE, f"Cannot create provider: {e}", fmt=fmt)
        return 2

    try:
        response = asyncio.run(provider.send(args.prompt))
    except Exception as e:
        error_output(ErrorCode.MODEL_UNAVAILABLE, f"Model test failed: {e}", fmt=fmt)
        return 2

    if fmt == "json":
        print(json.dumps({"status": "ok", "response": response.content}, default=str))
    else:
        print(f"Model '{args.name}' responded:")
        print(f"  {response.content}")

    return 0


def _models_remove(args, workspace: Path, fmt: str) -> int:
    """Remove a model configuration."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)

    try:
        store.delete_model(args.name)
    except FileNotFoundError:
        error_output(ErrorCode.MODEL_NOT_FOUND, f"Model '{args.name}' not found", fmt=fmt)
        return 2

    if fmt == "json":
        print(json.dumps({"status": "removed", "name": args.name}))
    else:
        print(f"Model '{args.name}' removed.")

    return 0


def _parse_connection(value: str) -> dict | None:
    """Parse connection config from JSON string or file path."""
    # Try as JSON first
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    # Try as file path
    path = Path(value)
    if path.exists():
        import yaml

        content = path.read_text()
        try:
            return yaml.safe_load(content)
        except Exception:
            try:
                return json.loads(content)
            except Exception:
                pass

    return None

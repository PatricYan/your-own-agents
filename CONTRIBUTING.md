# Contributing

## Setup

```bash
git clone https://github.com/your-org/your-own-agents.git
cd your-own-agents
conda env create -f environment.yml
conda activate agentpipe
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Commit Gates

Every commit must pass:

1. **Ruff lint** — `ruff check src/ tests/ --fix`
2. **Ruff format** — `ruff format src/ tests/`
3. **Pytest** — `pytest tests/ -k "not live"`
4. **Commit message** — [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)

```
feat(core): add new feature
fix(execution): fix timeout bug
docs: update README
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `build`, `chore`

## Project Structure

```
src/agentpipe/
  config.py        # reads .env via python-dotenv
  common/          # Message, ToolCall, ToolDefinition (no deps)
  core/            # Task, Pipeline, Permissions, Condition
  tools/           # 10 built-in tools + registry
  models/          # ModelProvider + streaming adapters
  execution/       # Agent loop, DAG engine, recovery, runner
  loader/          # YAML pipeline loader
  web/             # REST API + WebSocket (Starlette)
  cli/             # CLI commands
web/frontend/      # React + React Flow
```

## Adding a Tool

1. Create `src/agentpipe/tools/builtin/my_tool.py` — implement `Tool` ABC
2. Register in `src/agentpipe/tools/registry.py` `create_default_registry()`
3. Add permission mapping in `src/agentpipe/core/task.py` `Permissions._TOOL_MAP`

## Adding a Model Adapter

1. Create `src/agentpipe/models/adapters/my_provider.py` — implement `ModelProvider.chat()` with streaming
2. Add dispatch in `src/agentpipe/models/adapters/__init__.py`

## Adding a CLI Command

1. Create handler in `src/agentpipe/cli/`
2. Add subparser + dispatch in `src/agentpipe/cli/main.py`

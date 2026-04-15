# your-own-agents Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-14

## Active Technologies

- Python 3.11+ + asyncio (stdlib), pydantic (validation/serialization), pyyaml (config parsing), httpx (HTTP model calls), sqlite3 (stdlib, execution history) (001-agent-pipeline-framework)

## Project Structure

```text
src/
├── agentpipe/
│   ├── __init__.py          # Package exports
│   ├── __main__.py          # CLI entry point (python -m agentpipe)
│   ├── cli/
│   │   ├── main.py          # CLI argument parsing and command dispatch
│   │   ├── run.py           # 'run' command handler
│   │   ├── models.py        # 'models' command handler
│   │   ├── pipelines.py     # 'agents' and 'pipelines' command handlers
│   │   └── status.py        # 'status' command handler
│   ├── core/
│   │   ├── agent.py         # Agent entity (pipeline + models + tools)
│   │   ├── pipeline.py      # Pipeline/DAG definition and validation
│   │   ├── task.py          # Task definition (goal-based autonomous agent)
│   │   ├── condition.py     # Condition expression evaluation
│   │   └── constraint.py    # Constraint definitions and enforcement
│   ├── execution/
│   │   ├── agent_loop.py    # Core think-act-observe agentic loop
│   │   ├── conversation.py  # Message, ToolCall, Conversation models
│   │   ├── engine.py        # DAG executor (topological sort, async scheduling)
│   │   ├── runner.py        # Task runner (delegates to agent loop)
│   │   ├── recovery.py      # Three-tier recovery cascade
│   │   └── state.py         # Execution state machine
│   ├── models/
│   │   ├── registry.py      # Model configuration and registry
│   │   ├── provider.py      # Base ModelProvider (multi-turn + tool calling)
│   │   └── adapters/
│   │       ├── __init__.py  # Adapter factory
│   │       ├── openai.py    # OpenAI adapter (tool calling)
│   │       ├── anthropic.py # Anthropic adapter (tool use)
│   │       ├── ollama.py    # Ollama adapter
│   │       └── http.py      # Generic HTTP adapter
│   ├── tools/
│   │   ├── base.py          # Tool ABC, ToolDefinition schema
│   │   ├── registry.py      # ToolRegistry + default factory
│   │   └── builtin/
│   │       ├── file_read.py
│   │       ├── file_write.py
│   │       ├── shell.py
│   │       ├── web_fetch.py
│   │       └── submit_result.py
│   ├── storage/
│   │   ├── definitions.py   # YAML file storage for definitions
│   │   └── history.py       # SQLite execution history
│   └── loader/
│       ├── yaml_loader.py   # YAML pipeline loader
│       └── json_loader.py   # JSON pipeline loader
tests/
├── conftest.py              # Shared fixtures
├── unit/
├── contract/
└── integration/
```

## Commands

```bash
# Install
pip install -e ".[dev]"

# Lint
ruff check src/

# Format
ruff format src/ tests/

# Test
pytest

# Run CLI
python -m agentpipe --help
agentpipe --help
```

## Code Style

Python 3.11+: Follow standard conventions. Ruff configured with pycodestyle, pyflakes, isort, pep8-naming, pyupgrade, flake8-bugbear, flake8-simplify. Line length 100.

## Design Principles

1. **Each task is an agent** -- autonomous unit with its own model, tools, goal, and agentic loop
2. **Each agent has its own rules** -- model, tools, permissions, constraints, and system prompt are scoped per task
3. **Each task has its own dependencies** -- edges define data flow and execution order (DAG like Airflow)
4. **The task is the basic unit** -- self-contained, reusable, composable; a pipeline is just tasks wired together

## Key Patterns

- **Pydantic models** for all domain entities (Agent, Pipeline, TaskDefinition, ModelConfig)
- **Abstract base class** for ModelProvider (multi-turn chat + tool calling) and Tool
- **Agent Loop** (think-act-observe cycle): model reasons, calls tools, observes results, iterates
- **Per-task tool permissions** enforced at execution time (not just definition time)
- **asyncio** for concurrent agent execution within pipelines
- **Topological sort** (Kahn's algorithm) for DAG scheduling
- **Sandboxed eval** for condition expressions with restricted builtins
- **Three-tier recovery**: retry -> fallback model -> subtask decomposition
- **Tool registry** for built-in and custom tools with per-task tool restrictions
- **Multi-turn conversation** model: Message, ToolCall, ToolResult, Conversation

## Recent Changes

- 001-agent-pipeline-framework: Autonomous agent architecture where each task is an agent with model brain + tools + agentic loop

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

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
│   ├── common/              # Shared data types (no business logic)
│   │   ├── conversation.py  # Message, ToolCall, ToolResult, Conversation
│   │   └── tool_schema.py   # ToolDefinition, ToolParameter
│   ├── cli/
│   │   ├── main.py          # CLI argument parsing and command dispatch
│   │   ├── run.py           # 'run' command handler + InteractiveController
│   │   ├── models.py        # 'models' command handler
│   │   ├── pipelines.py     # 'agents' and 'pipelines' command handlers
│   │   └── status.py        # 'status' command handler
│   ├── core/
│   │   ├── agent.py         # Agent entity (pipeline + models + tools)
│   │   ├── pipeline.py      # Pipeline/DAG definition and validation
│   │   ├── task.py          # TaskDefinition + Permissions (OpenCode format)
│   │   ├── condition.py     # Condition expression evaluation
│   │   ├── constraint.py    # Constraint definitions and enforcement
│   │   └── visualize.py     # ASCII and Mermaid DAG rendering
│   ├── execution/
│   │   ├── agent_loop.py    # Core think-act-observe agentic loop
│   │   ├── conversation.py  # (shim: re-exports from common/)
│   │   ├── engine.py        # DAG executor (topological sort, async scheduling)
│   │   ├── runner.py        # Task runner (delegates to agent loop)
│   │   ├── recovery.py      # Three-tier recovery cascade
│   │   └── state.py         # Execution state machine
│   ├── models/
│   │   ├── registry.py      # Model configuration and registry
│   │   ├── provider.py      # Base ModelProvider (multi-turn + tool calling)
│   │   ├── http_session.py  # Connection pooling + retry
│   │   └── adapters/
│   │       ├── __init__.py  # Adapter factory
│   │       ├── openai.py    # OpenAI adapter (tool calling)
│   │       ├── anthropic.py # Anthropic adapter (tool use)
│   │       ├── ollama.py    # Ollama adapter
│   │       └── http.py      # Generic HTTP adapter
│   ├── tools/
│   │   ├── base.py          # Tool ABC (imports ToolDefinition from common/)
│   │   ├── registry.py      # ToolRegistry + default factory
│   │   └── builtin/
│   │       ├── file_read.py
│   │       ├── edit.py
│   │       ├── file_write.py
│   │       ├── file_delete.py
│   │       ├── shell.py
│   │       ├── glob.py
│   │       ├── grep.py
│   │       ├── list_dir.py
│   │       ├── web_fetch.py
│   │       └── submit_result.py
│   ├── storage/
│   │   ├── definitions.py   # YAML file storage for definitions
│   │   └── history.py       # SQLite execution history
│   ├── web/                  # REST API + WebSocket (Starlette)
│   │   ├── api.py
│   │   ├── state.py
│   │   └── serve.py
│   └── loader/
│       ├── yaml_loader.py   # YAML pipeline loader
│       └── json_loader.py   # JSON pipeline loader
tests/
├── conftest.py              # Shared fixtures + mock providers
├── test_schema.py           # Schema types (standalone)
├── test_permissions.py      # OpenCode-style permissions
├── test_core.py             # Task, Pipeline, Condition, Constraint
├── test_tools.py            # 10 built-in tools + registry
├── test_execution.py        # Agent loop, DAG engine, recovery
├── test_context_control.py  # Token budget, context window, session reuse
├── test_isolation.py        # Provider isolation, module independence
├── test_model_contract.py   # Contract tests with local mock HTTP server
├── test_storage.py          # Definition store, history store
├── test_loader.py           # YAML/JSON pipeline loading
├── test_web_api.py          # REST API endpoints
└── test_tutorial.py         # End-to-end integration
```

## Commands

```bash
# Install (conda)
conda env create -f environment.yml
conda activate agentpipe
pre-commit install --hook-type pre-commit --hook-type commit-msg

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
- **Skills as Markdown** — system_prompt files follow [karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) pattern (Principles + Loop + Success Criteria)
- **Per-purpose model routing** — `model_routing: {think: gpt-4o, tool_call: gpt-4o-mini}` per task
- **Per-task tool permissions** enforced at execution time (not just definition time)
- **Per-task provider isolation** — each task creates its own model provider (own HTTP session, own context)
- **Shared common/** — Message, ToolCall, ToolDefinition live in `common/` so all modules can import without circular deps
- **Token budget** (`max_tokens`) and **context window** (`context_window`) control per task
- **Conversation trimming** — old messages automatically removed when context grows too large
- **HTTP session reuse** within a task (connection pooling) + **retry with backoff** on transient errors
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

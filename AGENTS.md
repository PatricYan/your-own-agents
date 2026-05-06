# AgentPipe Development Guidelines

## Technologies

Python 3.11+, pydantic, pyyaml, httpx, python-dotenv, starlette, React, React Flow

## Commands

```bash
conda activate agentpipe
ruff check src/ tests/ --fix
ruff format src/ tests/
pytest -v
agentpipe serve
```

## Key Patterns

- **Each task is an agent** — model brain + tools + goal + prompts + permissions
- **Agent loop**: think → use tools → observe → repeat → submit_result
- **Streaming**: SSE-based model responses via httpx
- **Per-task isolation**: each agent gets its own provider instance
- **Config from .env**: python-dotenv loads `.env` automatically
- **Rules/prompts/permissions from files**: loaded from paths set in `.env` and pipeline YAML
- **Data flow with provenance**: upstream output keyed by task name
- **Conversation logs**: saved to `AGENTPIPE_LOGS_DIR` per task as JSON
- **WebSocket**: pushes task_status, task_content, task_tool_call, task_iteration to UI
- **Backend logging**: console shows task execution progress when running via API

## Configuration (all from .env)

```bash
AGENTPIPE_PIPELINES_DIR=examples
AGENTPIPE_MODELS=my_models.yaml
AGENTPIPE_RULES=prompts/agent_rules.md
AGENTPIPE_PERMISSIONS=permissions/default.yaml
AGENTPIPE_LOGS_DIR=logs
```

## Active Technologies
- Python 3.11+ (backend), TypeScript/React 18 (frontend) + Starlette (ASGI), httpx, pydantic, React Flow v12, React 18 (001-agent-pipeline-framework)
- In-memory (`ServerState` singleton) + JSONL log files on disk (001-agent-pipeline-framework)

## Recent Changes
- 001-agent-pipeline-framework: Added Python 3.11+ (backend), TypeScript/React 18 (frontend) + Starlette (ASGI), httpx, pydantic, React Flow v12, React 18

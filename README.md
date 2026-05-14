# AgentPipe

Build your own agent pipelines. Each task is an autonomous agent with a model as its brain and tools as its hands.

Inspired by [Airflow](https://airflow.apache.org/), [OpenCode](https://opencode.ai/), [Codex CLI](https://github.com/openai/codex), [karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills), and [autoresearch](https://github.com/karpathy/autoresearch).

## How It Works

1. You define a pipeline in a YAML file — tasks, models, goals, prompts, permissions
2. Each task is an autonomous agent that runs: **think → use tools → observe → repeat**
3. Tasks run in order based on `depends_on`. Independent tasks run in parallel
4. Each agent calls `submit_result` when done. Its output flows to downstream agents

## Setup

```bash
conda env create -f environment.yml
conda activate agentpipe
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Configuration

All configuration is in `.env`. Copy the example and edit:

```bash
cp .env.example .env
```

```bash
# .env
AGENTPIPE_HOST=0.0.0.0
AGENTPIPE_PORT=8420
# where pipeline YAML files are
AGENTPIPE_PIPELINES_DIR=examples
# models configuration file  
AGENTPIPE_MODELS=examples/models.yaml
# default agent behavior rules  
AGENTPIPE_RULES=examples/prompts/agent_rules.md
# default permissions  
AGENTPIPE_PERMISSIONS=examples/permissions/default.yaml
# conversation logs saved here  
AGENTPIPE_LOGS_DIR=logs  
AGENTPIPE_LOG_LEVEL=info
REACT_APP_API_URL=http://localhost:8420
```

## Step 1: Configure Models

Copy `examples/models.yaml` to `my_models.yaml`, uncomment your provider, fill in your key and endpoint:

```yaml
# my_models.yaml
models:
  - name: default
    provider: microsoft-foundry-anthropic
    connection:
      api_key: your-actual-api-key
      base_url: https://your-resource.services.ai.azure.com/anthropic/v1/messages
      model: model_name
```

Set `AGENTPIPE_MODELS=my_models.yaml` in `.env`.

The `api_key` is the actual key value. The `base_url` is the full API endpoint URL — the code uses it directly without appending any path.

Providers: `openai`, `anthropic`, `ollama`, `http`, etc

See `examples/models.yaml` for templates of all providers.

## Step 2: Define a Pipeline

```yaml
# examples/my-pipeline.yaml
name: my-pipeline
models: my_models.yaml

tasks:
  - name: step-1
    goal: goals/step1.md           # what this agent should do
    prompts:                       # how the agent should behave
      - prompts/agent_rules.md     # shared rules
      - prompts/code-reviewer.md   # role-specific skills
    primary_model: claude
    permissions: permissions/read-only.yaml
    max_iterations: 10

  - name: step-2
    goal: goals/step2.md
    prompts:
      - prompts/agent_rules.md
    primary_model: gpt
    permissions: permissions/developer.yaml
    depends_on: step-1             # runs after step-1 completes
    max_iterations: 15
```

### What each field does

| Field | Purpose |
|-------|---------|
| `goal` | What the agent should accomplish. File path (`.md`) or inline text |
| `prompts` | How the agent should behave. List of files loaded as system prompt |
| `primary_model` | Which model to use (name from models config) |
| `permissions` | What tools the agent can use. File path (`.yaml`) |
| `depends_on` | Which tasks must complete first. String or list |
| `max_iterations` | Max think-act-observe cycles |
| `max_tokens` | Total token budget. Loop stops if exceeded |
| `context_window` | Max conversation size. Old messages trimmed |

## Step 3: Run via CLI

```bash
agentpipe run examples/my-pipeline.yaml --watch
```

Output:

```
Pipeline: my-pipeline
Tasks: step-1 → step-2
  Level 0: [step-1] model=claude
  Level 1: [step-2] model=gpt (after: step-1)

============================================================
[step-1] Running... (model: claude)
============================================================
I'll start by reading the code...
  → file_read({'path': 'src/main.py'})
  [iteration 0] tools: file_read
  → grep({'pattern': 'def main', 'include': '*.py'})
  [iteration 1] tools: grep
  → submit_result({'result': '{"findings": [...]}'})

[step-1] Completed (25.6s)
  Output [findings]: [...]

============================================================
[step-2] Running... (model: gpt)
============================================================
  Input from [step-1]: {'findings': [...]}
```

Conversation logs saved to the directory set by `AGENTPIPE_LOGS_DIR`.

### CLI Commands

```bash
agentpipe run <pipeline.yaml> [--watch] [-i]    # run a pipeline
agentpipe validate <pipeline.yaml>               # validate YAML
agentpipe dag <pipeline.yaml> [--mermaid]        # view DAG
agentpipe serve                                  # start API server
```

## Step 4: Run via Web UI

Two separate services communicating via API:

```bash
# Terminal 1: backend API server
agentpipe serve

# Terminal 2: frontend
cd web/frontend && bun install && bun start
```

Open `http://localhost:3000`:
- Select a pipeline from the dropdown
- Click **Run**
- Watch nodes change color: grey → blue → green
- Click any node to see the conversation log
- Click **Pause** to stop, edit permissions/goal, then **Resume**

## Step 5: Run via Docker

```bash
cp .env.example .env       # set your config
docker compose up           # both services
docker compose up backend   # backend only
docker compose up frontend  # frontend only
```

## Step 6: Run via REST API

```bash
# List pipelines
curl http://localhost:8420/api/pipelines

# Run a pipeline
curl -X POST http://localhost:8420/api/pipelines/my-pipeline/run \
  -H 'Content-Type: application/json' -d '{}'

# Check status
curl http://localhost:8420/api/runs/<run_id>

# View task conversation logs
curl http://localhost:8420/api/runs/<run_id>/tasks/step-1/logs

# Pause / Resume
curl -X POST http://localhost:8420/api/runs/<run_id>/pause
curl -X POST http://localhost:8420/api/runs/<run_id>/resume

# Reload config after editing YAML files
curl -X POST http://localhost:8420/api/reload
```

## How Agents Work

Each agent runs a **think → act → observe → repeat** loop:

```
1. THINK: model receives goal + prompts + permissions + upstream data
2. ACT:   model calls tools (file_read, shell, edit, etc.)
3. OBSERVE: tool results are added to the conversation
4. REPEAT: until the agent calls submit_result or hits max_iterations
```

The agent **must call `submit_result`** to complete. If it responds with plain text instead of using tools, it gets re-prompted: "You must use tools. Call submit_result when done."

### System prompt structure

The system prompt sent to the model is built from:

1. **Rules** — loaded from `AGENTPIPE_RULES` file (think before acting, simplicity first, etc.)
2. **Task prompts** — loaded from the `prompts` list in the pipeline YAML
3. **Permissions** — auto-generated ("You CAN read files", "You CANNOT run shell commands")

### Data flow between agents

When task A completes, its output flows to dependent tasks with provenance:

```python
# Task B receives:
{"task-A": {"findings": [...], "status": "success"}}
```

Each upstream task's output is under its name — no key collisions.

### Conditional routing

Route to different tasks based on output:

```yaml
edges:
  - from: evaluate
    to: publish
    when:
      expression: "quality_score > 0.8"
  - from: evaluate
    to: improve
    when:
      expression: "quality_score <= 0.8"
```

## Tools (10 built-in)

| Tool | Permission | What it does |
|------|-----------|-------------|
| `file_read` | `read` | Read file contents |
| `edit` | `edit` | Edit file by exact string replacement |
| `file_write` | `edit` | Create or write files |
| `file_delete` | `edit` | Delete files |
| `shell` | `bash` | Execute shell commands |
| `glob` | `glob` | Find files by pattern |
| `grep` | `grep` | Search file contents by regex |
| `list` | `list` | List directory contents |
| `web_fetch` | `webfetch` | Fetch URL content |
| `submit_result` | always | Signal task completion |

## Permissions

Default: read-only. Set per-task via YAML file:

```yaml
# permissions/developer.yaml
"*": deny
read: allow
edit: allow
bash:
  "*": deny
  "git *": allow
  "pytest *": allow
```

Granular patterns: `"git *": allow` means `git status` is allowed, `git push` is allowed, but `curl` is denied.

## Prompts (Skills)

Each prompt file follows the [karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) pattern:

```markdown
# Code Reviewer

## Principles
- Think before acting
- Be specific (file paths, line numbers)

## Loop
1. Read files → verify
2. Analyze → verify
3. Submit findings

## Success Criteria
Done when all files reviewed and results submitted.
```

Layer multiple prompts per task:

```yaml
prompts:
  - prompts/agent_rules.md       # shared across all agents
  - prompts/code-reviewer.md     # role-specific
```

## Architecture

```
src/agentpipe/
├── common/         # Shared types (no dependencies)
├── core/           # Task, Pipeline, Permissions
├── tools/          # 10 built-in tools
├── models/         # Model adapters (streaming)
├── execution/      # Agent loop, DAG engine
├── loader/         # YAML loader
├── web/            # REST API + WebSocket
└── cli/            # CLI commands

web/frontend/       # React + React Flow (separate service)
```

## License

Apache-2.0

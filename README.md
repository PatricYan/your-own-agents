# AgentPipe

Build your own agent pipelines. Inspired by [Airflow](https://airflow.apache.org/), [OpenCode](https://opencode.ai/), and [Codex CLI](https://github.com/openai/codex).

**The idea:** Airflow orchestrates tasks in a DAG. OpenCode and Codex CLI are autonomous agents that use models and tools to get things done. AgentPipe combines both -- **each task in the pipeline is an autonomous agent** that thinks, acts, and self-corrects until its goal is met.

## Core Principles

### 1. Each task is an agent

A task is not a prompt. It is an autonomous agent with its own **model** (brain), **tools** (hands), and **goal**. The agent runs a think-act-observe loop: the model reasons about what to do, calls tools to interact with the world, observes the results, and repeats until the goal is accomplished.

### 2. Each agent has its own rules, permissions, and models

Every task defines independently:

- **Permissions** (like OpenCode): granular control over file_read, file_write, file_delete, shell, web_fetch
- **Which model** to use (GPT-4o, Claude, Ollama, any HTTP endpoint)
- **Constraints** (timeout, max retries, max iterations, quality thresholds)
- **System prompt** (persona, behavioral rules)
- **Fallback models** if the primary fails

Permissions follow OpenCode's model: each tool is set to `allow`, `ask`, or `deny`.

- `allow` — tool runs without approval
- `ask` — tool requires user approval (in `--interactive` mode)
- `deny` — tool is blocked; model sees an error if it tries

```yaml
tasks:
  - name: code-reviewer
    goal: goals/review-code.md
    system_prompt: prompts/security-engineer.md
    primary_model: gpt-4o
    permissions: permissions/reviewer.yaml
    max_iterations: 10

  - name: code-fixer
    goal: goals/fix-code.md
    system_prompt: prompts/code-fixer.md
    primary_model: claude-sonnet
    fallback_models: [gpt-4o]
    permissions: permissions/developer.yaml
    max_iterations: 20
```

### 3. Each task has its own dependencies

Dependencies are declared Airflow-style using `depends_on` directly on the task. A task can have 1 or more dependencies. Independent tasks run in parallel. Data flows from upstream to downstream.

```yaml
tasks:
  - name: research
    goal: goals/gather-info.md
    primary_model: gpt-4o
    # no depends_on → runs first (entry task)

  - name: write-code
    goal: goals/write-implementation.md
    primary_model: claude-sonnet
    permissions: permissions/developer.yaml
    depends_on: research              # 1 dependency (string)

  - name: write-tests
    goal: goals/write-tests.md
    primary_model: gpt-4o
    permissions: permissions/developer.yaml
    depends_on: research              # also depends on research (parallel with write-code)

  - name: integrate
    goal: goals/integrate-and-verify.md
    primary_model: gpt-4o
    permissions: permissions/tester.yaml
    depends_on: [write-code, write-tests]   # 2+ dependencies (list)
```

For **conditional routing** (e.g., go to A if score > 0.8, else go to B), use explicit edges with conditions:

```yaml
edges:
  - source: evaluate
    target: publish
    condition:
      expression: "quality_score > 0.8"
  - source: evaluate
    target: improve
    condition:
      expression: "quality_score <= 0.8"
```

Both `depends_on` and explicit `edges` can be used in the same pipeline.

### 4. The task is the basic unit

Everything revolves around the task. A task is self-contained: it knows its goal, its model, its tools, and its rules. You can:

- Define a task once and reuse it across pipelines (`is_reusable: true`)
- Nest a sub-pipeline inside a task (composition)
- Run a single task standalone or wire many into a pipeline
- Each task produces structured output that downstream tasks consume

## How It Works

```
Pipeline DAG (like Airflow)
    |
    v
[ Task 1 ]  ------>  [ Task 2 ]  ------>  [ Task 3 ]
  Agent               Agent                Agent
  - model: gpt-4o     - model: claude      - model: gpt-4o
  - tools: [web]       - tools: [file,sh]   - tools: [sh,file]
  - rules: read-only   - rules: can write   - rules: can run tests
    |                    |                    |
    v                    v                    v
  Think -> Act ->      Think -> Act ->      Think -> Act ->
  Observe -> Repeat    Observe -> Repeat    Observe -> Repeat
```

Each agent autonomously:
1. **Thinks**: the model reasons about the goal and decides what to do
2. **Acts**: calls tools (read files, run commands, fetch URLs)
3. **Observes**: sees the tool output and decides next step
4. **Repeats**: until the goal is met or limits are hit

## Documentation

- **[Tutorial](docs/tutorial.md)** — Step-by-step guide to configure, run, and verify every feature
- **[Contributing](CONTRIBUTING.md)** — Project structure, code style, how to add tools/adapters/commands
- **[Examples](examples/)** — 6 ready-to-run pipeline YAML files

## Installation

```bash
git clone https://github.com/your-org/your-own-agents.git
cd your-own-agents

# Create conda environment (Python 3.11 + Node.js 20 + all deps)
conda env create -f environment.yml
conda activate agentpipe

# Install git hooks and build frontend
make post-setup
```

Or step by step without Make:

```bash
conda env create -f environment.yml
conda activate agentpipe
pre-commit install --hook-type pre-commit --hook-type commit-msg
cd web/frontend && npm install && npm run build && cd ../..
```

## Quick Start

### 1. Register models

```bash
agentpipe models register gpt-4o \
  --provider openai \
  --connection '{"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o"}'

agentpipe models register local-llama \
  --provider ollama \
  --connection '{"base_url": "http://localhost:11434", "model": "llama3"}'
```

### 2. Define a pipeline

```yaml
# my-pipeline.yaml
name: research-and-summarize
execution_strategy: fail_fast

tasks:
  - name: research
    goal: goals/research.md
    system_prompt: prompts/researcher.md
    primary_model: gpt-4o
    permissions:
      "*": deny
      read: allow
      glob: allow
      webfetch: allow
    max_iterations: 10

  - name: summarize
    goal: goals/summarize.md
    primary_model: local-llama
    # no permissions override → default read-only
    depends_on: research
    max_iterations: 5
```

### 3. Run it

```bash
agentpipe agents create my-researcher --pipeline my-pipeline.yaml
agentpipe run my-researcher --input '{"topic": "AI agents 2026"}' --watch
```

## Python API

```python
import asyncio
from agentpipe import Agent, Pipeline, TaskDefinition, Permissions, ModelConfig

pipeline = Pipeline(
    name="code-pipeline",
    tasks=[
        TaskDefinition(
            name="write",
            goal="goals/write-function.md",       # loaded from file
            primary_model="gpt-4o",
            permissions=Permissions({"*": "deny", "read": "allow", "edit": "allow"}),
            max_iterations=10,
        ),
        TaskDefinition(
            name="test",
            goal="goals/test-and-fix.md",          # loaded from file
            primary_model="gpt-4o",
            permissions=Permissions({"*": "deny", "read": "allow", "edit": "allow", "bash": "allow"}),
            depends_on=["write"],
            max_iterations=15,
        ),
    ],
)

agent = Agent(
    name="coder",
    pipeline=pipeline,
    model_configs=[
        ModelConfig(name="gpt-4o", provider="openai",
                    connection={"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o"}),
    ],
)

result = asyncio.run(agent.execute({"problem": "fibonacci sequence generator"}))
```

## Task Configuration Reference

```yaml
- name: task-name
  goal: goals/my-goal.md                            # file path (.md, .txt)
  system_prompt: prompts/my-prompt.md                # file path (.md, .txt, .prompt)
  permissions: permissions/my-perms.yaml             # file path (.yaml, .json)
  models: [gpt-4o, claude, llama]                   # ordered: primary, fallback1, fallback2
  depends_on: upstream-task                         # or [a, b] for multiple
  max_iterations: 20                                # max think-act-observe cycles
  max_tool_calls: 50                                # max total tool invocations
  max_tokens: 50000                                 # total token budget; loop stops if exceeded
  context_window: 8000                              # max tokens in conversation; old messages trimmed
  constraints:
    - type: timeout
      value: 300
      on_violation: fail
```

Keep your pipeline YAML clean. All the detail lives in files:

```
examples/
├── goals/           # what each agent should accomplish
│   ├── research.md
│   ├── review-code.md
│   ├── fix-code.md
│   ├── write-implementation.md
│   ├── write-tests.md
│   └── ...
├── prompts/         # agent persona and behavioral rules
│   ├── code-reviewer.md
│   ├── code-fixer.md
│   ├── researcher.md
│   └── ...
└── permissions/     # what each agent can do (OpenCode format)
    ├── read-only.yaml
    ├── reviewer.yaml
    ├── developer.yaml
    ├── tester.yaml
    └── full-access.yaml
```

## Permissions

Follows [OpenCode's permission format](https://opencode.ai/docs/permissions) exactly. Each rule resolves to `allow`, `ask`, or `deny`.

### Simple: set all tools at once

```yaml
permissions: allow
```

### Per-tool: global default + overrides

```yaml
permissions:
  "*": ask             # default for tools not listed
  read: allow
  edit: deny
  bash: deny
```

### Granular: wildcard patterns within a tool

```yaml
permissions:
  "*": allow
  bash:
    "*": deny          # deny shell by default
    "git *": allow     # but allow git commands
    "npm *": allow     # and npm
    "pytest *": allow  # and pytest
    "rm *": deny       # explicitly deny rm
  webfetch: deny
```

Rules are matched by pattern. Last matching pattern wins (same as OpenCode).

### Permission keys

By default, tasks are **read-only**. Everything destructive is denied unless you explicitly grant it.

| Key | Default | Controls |
|-----|---------|----------|
| `read` | **allow** | Read files |
| `glob` | **allow** | Find files by pattern |
| `grep` | **allow** | Search file contents |
| `list` | **allow** | List directories |
| `submit_result` | **allow** | Signal task completion |
| `edit` | deny | Edit, write, create, delete files |
| `bash` | deny | Execute shell commands |
| `webfetch` | deny | Fetch URLs |
| `task` | deny | Launch sub-agents |
| `*` (everything else) | deny | Any tool not listed above |

If you set `tools: [...]` explicitly, that overrides the permissions-derived tool list.

## Built-in Tools

| Tool | Permission key | Description |
|------|---------------|-------------|
| `file_read` | `read` | Read file contents (with offset/limit) |
| `edit` | `edit` | Edit files by exact string replacement |
| `file_write` | `edit` | Write/create files and directories |
| `file_delete` | `edit` | Delete files |
| `shell` | `bash` | Execute shell commands (with timeout) |
| `glob` | `glob` | Find files by glob pattern |
| `grep` | `grep` | Search file contents by regex |
| `list` | `list` | List files and directories |
| `web_fetch` | `webfetch` | Fetch content from a URL |
| `submit_result` | `submit_result` | Signal task completion with output |

## Updating an Agent Mid-Run

You can modify permissions, goal, or system prompt **while the agent is running**. Changes take effect at the next think-act-observe iteration.

### CLI: Interactive Mode

Run with `--interactive` (or `-i`). Press **Ctrl+C** at any time to pause:

```bash
agentpipe run my-agent --input '{"task": "build a web scraper"}' --interactive
```

When paused:

```
--- PAUSED at [code-writer] iteration 3 ---
  Goal: Write a web scraper for the given site
  Model: gpt-4o
  Permissions: read=True write=True delete=False shell=False web=False

Commands:
  r / resume        - Continue autonomous execution
  p <perm> <on|off> - Toggle permission (e.g. 'p shell on')
  g <new goal>      - Update the goal
  s <new prompt>    - Update the system prompt
  q / quit          - Abort the pipeline

> p shell on
  shell = True
> g Write a web scraper and run it to verify it works
  Goal updated
> r
```

After you type `r`, the agent continues running autonomously with the new permissions and goal.

### Python API: on_before_iteration Hook

```python
from agentpipe.core.task import Permissions

def on_before(iteration, task):
    if iteration == 5:
        # Grant shell after 5 iterations
        return task.model_copy(update={
            "permissions": Permissions(file_read=True, file_write=True, shell=True)
        })
    if iteration == 10:
        # Change the goal mid-run
        return task.model_copy(update={
            "goal": "Wrap up and submit whatever you have so far"
        })
    return None  # no changes

result = asyncio.run(agent.execute(input_data, on_before_iteration=on_before))
```

The hook fires before every iteration. Return a modified task to change anything, or `None` to keep running as-is.

### What You Can Update Mid-Run

| Field | Effect |
|-------|--------|
| `permissions` | Immediately changes which tools the agent can use |
| `goal` | Injects a new goal message into the conversation |
| `system_prompt` | Injects updated instructions into the conversation |
| `tools` | Changes the explicit tool list (overrides permissions) |
| `max_iterations` | Changes the iteration limit |
| `max_tool_calls` | Changes the tool call limit |

### Autonomous After Resume

Once you resume (or if you never interrupt), the agent runs fully autonomously — thinking, using tools, self-correcting, and adapting until the goal is met or limits are reached. No human input needed.

## Recovery

When an agent fails, three-tier recovery kicks in:

1. **Retry**: re-run the agent loop from scratch (same model, exponential backoff)
2. **Fallback model**: switch to the next model in `fallback_models`
3. **Subtask decomposition**: ask a model to break the problem into smaller pieces

## Token and Context Control

When agents run many iterations, the conversation grows and can exceed the model's context window. Two controls prevent this:

**`max_tokens`** — total token budget for the agent. The loop stops when the accumulated token usage exceeds this limit:

```yaml
  max_tokens: 50000       # stop after spending 50K tokens total
```

**`context_window`** — maximum tokens in the conversation sent to the model. When exceeded, older messages are automatically trimmed:

```yaml
  context_window: 8000    # keep conversation under 8K tokens
```

Trimming strategy:
1. System prompt is always preserved (it's the agent's identity)
2. Oldest non-system messages are removed first
3. Recent messages are kept (the model needs recent context)

Token usage is tracked per agent and reported in the result:

```python
result = await agent.execute(input_data)
# result includes: total_tokens, prompt_tokens, completion_tokens
```

## Agent Isolation

Each agent-task in a pipeline runs in complete isolation:

- **Own provider instance** — each task creates its own HTTP session and connection to the model API
- **Own conversation** — no message history shared between agents
- **Own tool context** — tool calls don't leak between parallel agents
- **Data flows only through the DAG** — upstream output becomes downstream input, nothing else is shared

This means parallel agents (tasks at the same level in the DAG) never interfere with each other.

## View the Pipeline DAG

Like Airflow's graph view, you can visualize your pipeline as a DAG.

### Terminal (ASCII)

```bash
agentpipe pipelines dag my-pipeline.yaml
```

```
Pipeline: code-review-pipeline
Strategy: fail_fast

  [ analyze (gpt-4o) ]
      |
    analyze --> fix-bugs
    analyze --> fix-style
      |
  [ fix-bugs (claude-sonnet) ]    [ fix-style (gpt-4o) ]
      |
    fix-bugs --> run-tests
    fix-style --> run-tests
      |
  [ run-tests (gpt-4o) ]
      |
    run-tests --> report
      |
  [ report (gpt-4o) ]

Tasks:
  analyze: model=gpt-4o  perms=[read, glob, grep]  depends_on=(entry)  max_iter=20
  fix-bugs: model=claude-sonnet  perms=[read, edit, write]  depends_on=analyze  max_iter=20
  run-tests: model=gpt-4o  perms=[read, bash]  depends_on=fix-bugs, fix-style  max_iter=20
  report: model=gpt-4o  perms=[read, write]  depends_on=run-tests  max_iter=20
```

### Mermaid (GitHub, Notion, mermaid.live)

```bash
agentpipe pipelines dag my-pipeline.yaml --mermaid
```

Output:

````
graph TD
    analyze["analyze<br/>model: gpt-4o"]
    fix_bugs["fix-bugs<br/>model: claude-sonnet"]
    fix_style["fix-style<br/>model: gpt-4o"]
    run_tests["run-tests<br/>model: gpt-4o"]
    report["report<br/>model: gpt-4o"]
    analyze --> fix_bugs
    analyze --> fix_style
    fix_bugs --> run_tests
    fix_style --> run_tests
    run_tests --> report
````

Paste the output into any Mermaid renderer to see an interactive diagram.

### Python API

```python
pipeline = Pipeline(...)
print(pipeline.render_dag())          # ASCII
print(pipeline.render_dag("mermaid")) # Mermaid
```

## Web UI (like Airflow / n8n)

AgentPipe includes a web interface inspired by Airflow's DAG view and n8n's node canvas.

### Start the server

```bash
# Build the frontend (first time only)
cd web/frontend && npm install && npm run build && cd ../..

# Start the server
agentpipe serve
```

Opens at `http://localhost:8420` with:

- **Interactive DAG canvas** — drag-and-zoom node graph (React Flow), same visual style as n8n
- **Live execution** — nodes change color in real time as tasks run (pending → running → completed/failed)
- **Click any node** to see and edit: goal, permissions, model, system prompt, iteration count
- **Run/Pause/Resume** toolbar — control the pipeline like Airflow's trigger/pause buttons
- **Live updates via WebSocket** — no page refresh needed

### What you can do in the UI

| Action | How |
|--------|-----|
| View the DAG | Select a pipeline from the dropdown |
| Run a pipeline | Click **Run**, optionally enter JSON input |
| Watch live execution | Nodes light up as tasks run, edges animate |
| Pause mid-execution | Click **Pause** — the pipeline stops between iterations |
| Resume execution | Click **Resume** — continues autonomously |
| Edit a task mid-run | Click a node → change goal, permissions, prompt → **Apply Changes** |
| View task details | Click any node to open the sidebar with model, permissions, iteration, duration |

### REST API

All UI actions are backed by a REST API you can call directly:

```bash
# List pipelines
GET  /api/pipelines

# Get pipeline DAG (nodes + edges + levels)
GET  /api/pipelines/{name}

# Run a pipeline
POST /api/pipelines/{name}/run   {"input": {"topic": "AI"}}

# List runs
GET  /api/runs

# Get run status
GET  /api/runs/{run_id}

# Pause / Resume
POST /api/runs/{run_id}/pause
POST /api/runs/{run_id}/resume

# Update a task mid-run (permissions, goal, prompt)
PATCH /api/runs/{run_id}/tasks/{task_name}
      {"permissions": {"bash": "allow"}, "goal": "new goal"}

# List models
GET  /api/models

# WebSocket for live events
WS   /ws
```

## Architecture

```
src/agentpipe/
├── schema/         # Shared data types (Message, ToolCall, ToolDefinition) — no dependencies
├── core/           # Task, Pipeline, Permissions, Condition, Constraint — depends on schema/
├── tools/          # Tool ABC + 10 built-in tools + registry — depends on schema/
├── models/         # ModelProvider + adapters (OpenAI, Anthropic, Ollama, HTTP) — depends on schema/
├── execution/      # Agent loop, DAG engine, recovery, conversation window — depends on all above
├── storage/        # YAML definitions + SQLite history — standalone
├── loader/         # YAML/JSON pipeline loaders — depends on core/
├── web/            # REST API + WebSocket (Starlette) — depends on execution/
└── cli/            # CLI commands (run, agents, models, pipelines, status, serve) — top level

web/frontend/       # React + React Flow (n8n-style DAG canvas)
```

Each layer only depends on layers below it. Any module can be imported and used independently.

## CLI

```bash
agentpipe models register <name> --provider <type> --connection <json>
agentpipe agents create <name> --pipeline <file>
agentpipe run <agent> --input <json> [--watch] [--interactive] [--timeout <sec>]
agentpipe pipelines validate <file>
agentpipe pipelines dag <file> [--mermaid]
agentpipe status list [agent] [--limit N]
agentpipe status show <run-id>
agentpipe serve [--host 0.0.0.0] [--port 8420]
```

## Development

```bash
conda activate agentpipe

make lint           # ruff check + auto-fix
make format         # ruff format
make test           # pytest -v
make serve          # start web UI
make frontend       # rebuild React frontend
make check          # run all checks (lint + tests + example validation)
```

See `make help` for all commands.

### Commit Gates

Every `git commit` is automatically gated by pre-commit hooks. No commit goes through unless all pass.

| Gate | What runs | Blocks if |
|------|----------|-----------|
| **Ruff lint** | `ruff check --fix` on staged Python files | Unfixable lint errors |
| **Ruff format** | `ruff format` on staged Python files | Code not formatted |
| **File hygiene** | Trailing whitespace, YAML/JSON syntax, merge conflicts, debug statements | Any violation |
| **Unit tests** | `pytest tests/ --tb=short -q` | Any test fails |
| **Commit message** | [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format | Wrong format |

Commit message format: `<type>(<scope>): <description>`

```
feat(core): add token budget control        # new feature
fix(execution): handle timeout in loop       # bug fix
docs: update tutorial                        # docs only
refactor(models): extract http session       # restructuring
test(tools): add grep tool tests             # tests
build: update conda environment              # dependencies
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

Scopes (optional): `core`, `execution`, `tools`, `models`, `schema`, `cli`, `web`, `docs`

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## Requirements

All managed by `environment.yml` + `pyproject.toml`:

- **Conda**: Python 3.11, Node.js 20
- **Python**: pydantic, httpx, pyyaml, starlette, uvicorn, ruff, pytest, pre-commit, commitizen
- **Node**: React, React Flow (installed via `npm install` in `web/frontend/`)

## License

Apache-2.0

# AgentPipe

Build your own agent pipelines. Inspired by [Airflow](https://airflow.apache.org/), [OpenCode](https://opencode.ai/), and [Codex CLI](https://github.com/openai/codex).

**The idea:** Airflow orchestrates tasks in a DAG. OpenCode and Codex CLI are autonomous agents that use models and tools to get things done. AgentPipe combines both -- **each task in the pipeline is an autonomous agent** that thinks, acts, and self-corrects until its goal is met.

## Core Principles

### 1. Each task is an agent

A task is not a prompt. It is an autonomous agent with its own **model** (brain), **tools** (hands), and **goal**. The agent runs a think-act-observe loop: the model reasons about what to do, calls tools to interact with the world, observes the results, and repeats until the goal is accomplished.

### 2. Each agent has its own rules, permissions, and models

Every task defines independently:

- **Permissions** (like [OpenCode](https://opencode.ai/docs/permissions)): granular control over file_read, file_write, file_delete, shell, web_fetch
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
  - name: reviewer
    goal: examples/goals/research.md
    system_prompt: examples/prompts/code-reviewer.md
    permissions: examples/permissions/reviewer.yaml
    models: [gpt-4o, claude]
```

### 3. Each task has its own dependencies

Dependencies are declared Airflow-style using `depends_on` directly on the task. A task can have 1 or more dependencies. Independent tasks run in parallel. Data flows from upstream to downstream.

```yaml
tasks:
  - name: research
    goal: examples/goals/gather-info.md
    primary_model: gpt-4o
    # no depends_on → runs first (entry task)

  - name: write-code
    goal: examples/goals/write-implementation.md
    primary_model: claude-sonnet
    permissions: examples/permissions/developer.yaml
    depends_on: research              # 1 dependency (string)

  - name: write-tests
    goal: examples/goals/write-tests.md
    primary_model: gpt-4o
    permissions: examples/permissions/developer.yaml
    depends_on: research              # also depends on research (parallel with write-code)

  - name: integrate
    goal: examples/goals/integrate-and-verify.md
    primary_model: gpt-4o
    permissions: examples/permissions/tester.yaml
    depends_on: [write-code, write-tests]   # 2+ dependencies (list)
```

For **conditional routing** (e.g., go to A if score > 0.8, else go to B), use explicit edges with conditions:

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

Both `depends_on` and explicit `edges` can be used in the same pipeline.

### 4. The task is the basic unit

Everything revolves around the task. A task is self-contained: it knows its goal, its model, its tools, and its rules. You can:

- Define a task once and reuse it across pipelines (`is_reusable: true`)
- Nest a sub-pipeline inside a task (composition)
- Run a single task standalone or wire many into a pipeline
- Each task produces structured output that downstream tasks consume

### How to Build a Pipeline

A pipeline is a list of tasks connected by dependencies. Here's how to build one step by step.

**Step 1: Define tasks.** Each task is an agent with a goal:

```yaml
tasks:
  - name: research
    goal: examples/goals/research.md
    primary_model: default

  - name: write
    goal: examples/goals/write-implementation.md
    primary_model: default
```

With no dependencies, both tasks would run in parallel. Usually you want ordering.

**Step 2: Add dependencies with `depends_on`.** This is the primary way to connect tasks:

```yaml
  - name: write
    goal: examples/goals/write-implementation.md
    primary_model: default
    depends_on: research         # write runs after research completes
```

`depends_on` accepts a single task name or a list:

```yaml
    depends_on: research              # single dependency
    depends_on: [write, test]         # multiple dependencies — waits for all
```

**Step 3: Add conditional routing with `edges`.** When the next step depends on an agent's output, use explicit edges with `when`:

```yaml
edges:
  - from: evaluate                    # upstream task
    to: deploy                        # downstream task
    when:                             # condition on the upstream output
      expression: "quality_score > 0.8"
      description: "Deploy only if quality is high"
  - from: evaluate
    to: fix
    when:
      expression: "quality_score <= 0.8"
```

The `when.expression` is a Python expression evaluated against the upstream task's output dict. If it evaluates to `True`, that edge is followed. If `False`, the downstream task is skipped.

**Step 4: Control execution.**

```yaml
name: my-pipeline
execution_strategy: fail_fast    # stop on first failure (or: continue_on_failure)
max_concurrency: 3               # max 3 agents running in parallel
```

**Step 5: Verify the DAG.**

```bash
agentpipe pipelines dag my-pipeline.yaml
```

### Tasks vs Edges — Summary

| | Task | Edge |
|-|------|------|
| **What** | An autonomous agent (goal + model + tools + permissions) | A dependency between two tasks |
| **Defined by** | `tasks:` list in YAML | `depends_on` on the task, or `edges:` block |
| **When to use** | Always — every unit of work is a task | `depends_on` for ordering; `edges` for conditional routing |
| **Runs** | Autonomously (think-act-observe loop) | Automatically when upstream task completes |

**Rule of thumb:** Use `depends_on` for everything. Only add explicit `edges` when you need conditional branching based on an agent's output.

### Data Flow Between Tasks

When a task completes, its output becomes the input for downstream tasks:

```
[research] → output: {"findings": [...], "summary": "..."}
     |
     ↓ (output flows as input)
[write]   → receives: {"findings": [...], "summary": "..."} as input
```

- The agent calls `submit_result` with a JSON output — that becomes the task's output
- If a task has multiple upstream dependencies, their outputs are merged into one dict
- If a task has no `depends_on`, it receives the pipeline's initial input

### Edge Reference

**YAML syntax:**

```yaml
edges:
  - from: task-a               # upstream task name
    to: task-b                 # downstream task name
    when:                      # optional condition
      expression: "score > 0.8"
      description: "Only if score is high"
```

**Python syntax:**

```python
from agentpipe import Edge, Condition

Edge(
    upstream="task-a",
    downstream="task-b",
    condition=Condition(expression="score > 0.8", description="Only if score is high"),
)
```

**Complete example** — see `examples/08-combined.yaml` for a pipeline using both `depends_on` and conditional `edges` together.

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
- **[Examples](examples/)** — 9 ready-to-run pipeline YAML files

## Installation

### Backend

```bash
git clone https://github.com/your-org/your-own-agents.git
cd your-own-agents

# Create conda environment
conda env create -f environment.yml
conda activate agentpipe

# Install git hooks
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### Frontend (separate service)

```bash
cd web/frontend
npm install
```

Configure the backend URL in `web/frontend/.env`:

```
REACT_APP_API_URL=http://localhost:8420
```

## Quick Start

### 1. Configure models

Create `models.yaml` (or use the example: `examples/models.yaml`):

```yaml
models:
  - name: default
    provider: openai
    connection:
      api_key_env: OPENAI_API_KEY
      model: gpt-4o-mini
```

Set your API key:

```bash
export OPENAI_API_KEY="sk-..."
```

### 2. Define a pipeline

```yaml
# my-pipeline.yaml
name: research-and-summarize
execution_strategy: fail_fast
models_file: models.yaml               # load models from config file

tasks:
  - name: research
    goal: examples/goals/research.md
    system_prompt: examples/prompts/researcher.md
    primary_model: default
    max_iterations: 10

  - name: summarize
    goal: examples/goals/summarize.md
    primary_model: default
    depends_on: research
    max_iterations: 5
```

### 3. Run it

```bash
agentpipe run my-pipeline.yaml --input '{"topic": "AI agents"}' --watch
```

No registration needed. One YAML file, one command.

## Model Configuration

Models are defined in configuration files. Three ways to provide them:

### 1. Separate models file (recommended — shared across pipelines)

```yaml
# models.yaml
models:
  - name: gpt-4o
    provider: openai
    connection:
      api_key_env: OPENAI_API_KEY
      model: gpt-4o
  - name: claude
    provider: anthropic
    connection:
      api_key_env: ANTHROPIC_API_KEY
      model: claude-sonnet-4-20250514
  - name: local-llama
    provider: ollama
    connection:
      base_url: http://localhost:11434
      model: llama3
```

Reference from pipeline:

```yaml
models_file: models.yaml
```

Or pass on the command line:

```bash
agentpipe run pipeline.yaml --models models.yaml
```

### 2. Inline in the pipeline YAML

```yaml
name: my-pipeline
models:
  - name: default
    provider: openai
    connection:
      api_key_env: OPENAI_API_KEY
      model: gpt-4o-mini
tasks:
  - name: agent-1
    goal: examples/goals/research.md
    primary_model: default
```

### 3. CLI registration (legacy)

```bash
agentpipe models register default --provider openai --connection '{"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"}'
```

Supported providers: `openai`, `anthropic`, `ollama`, `http`

## Python API

```python
import asyncio
from agentpipe import Agent, Pipeline, TaskDefinition, Permissions, ModelConfig

pipeline = Pipeline(
    name="code-pipeline",
    tasks=[
        TaskDefinition(
            name="write",
            goal="examples/goals/write-function.md",
            primary_model="gpt-4o",
            permissions=Permissions({"*": "deny", "read": "allow", "edit": "allow"}),
            max_iterations=10,
        ),
        TaskDefinition(
            name="test",
            goal="examples/goals/test-and-fix.md",
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

## Skills and Prompts

The `system_prompt` file is the agent's **skill** — it programs the agent's behavior, inspired by [karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) and [autoresearch](https://github.com/karpathy/autoresearch).

A good skill file has four sections:

```markdown
# Role Name
One-line description.

## Principles
- Think Before Acting — state assumptions, don't guess
- Simplicity First — minimum change that solves the problem
- Surgical Changes — touch only what you must

## Loop
1. [Step] → verify: [check]
2. [Step] → verify: [check]

## Success Criteria
Done when: [measurable conditions]
```

See `examples/prompts/` for complete skill files:
- `code-reviewer.md` — read-only review with severity ratings
- `code-fixer.md` — surgical fixes with verification loop
- `researcher.md` — hypothesis-driven research with structured output
- `autonomous-researcher.md` — self-improving experiment loop (autoresearch pattern)

## Model Routing

Each task can use **different models for different purposes**, like OpenCode uses different models for reasoning vs tool calls.

```yaml
tasks:
  - name: implement
    goal: examples/goals/write-implementation.md
    system_prompt: examples/prompts/code-fixer.md
    primary_model: claude                   # default model
    model_routing:
      think: claude                         # best model for reasoning
      tool_call: gpt-4o-mini               # fast/cheap model for tool calls
      summarize: gpt-4o                    # model for final summary
    permissions: examples/permissions/developer.yaml
```

The `primary_model` is used by default. `model_routing` overrides it for specific purposes. See `examples/09-model-routing.yaml` for a complete example.

## Task Configuration Reference

```yaml
- name: task-name
  goal: examples/goals/my-goal.md                    # agent's objective
  system_prompt: examples/prompts/my-skill.md        # agent's behavioral skill
  permissions: examples/permissions/my-perms.yaml    # what the agent can do
  models: [gpt-4o, claude, llama]                   # ordered: primary, fallback1, fallback2
  model_routing:                                    # per-purpose model assignment
    think: gpt-4o
    tool_call: gpt-4o-mini
  depends_on: upstream-task                         # or [a, b] for multiple
  max_iterations: 20                                # max think-act-observe cycles
  max_tool_calls: 50                                # max total tool invocations
  max_tokens: 50000                                 # total token budget
  context_window: 8000                              # conversation window size
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
agentpipe run my-pipeline.yaml --input '{"task": "build a web scraper"}' --interactive
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
            "permissions": Permissions({"*": "deny", "read": "allow", "edit": "allow", "bash": "allow"})
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

## Backend (API Server)

The backend is a separate service. It serves the API and WebSocket only.

```bash
# Start
agentpipe serve
# API:  http://0.0.0.0:8420/api/pipelines
# WS:   ws://0.0.0.0:8420/ws

# Custom host and port
agentpipe serve --host 127.0.0.1 --port 9000
```

### REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/pipelines` | List all agents |
| `GET` | `/api/pipelines/{name}` | Get DAG (nodes, edges, levels) |
| `POST` | `/api/pipelines/{name}/run` | Start execution |
| `GET` | `/api/runs` | List all runs |
| `GET` | `/api/runs/{run_id}` | Get run status |
| `POST` | `/api/runs/{run_id}/pause` | Pause |
| `POST` | `/api/runs/{run_id}/resume` | Resume |
| `PATCH` | `/api/runs/{run_id}/tasks/{name}` | Update task mid-run |
| `GET` | `/api/models` | List models |
| `WS` | `/ws` | Live task status events |

```bash
curl -X POST http://localhost:8420/api/pipelines/my-agent/run \
  -H 'Content-Type: application/json' \
  -d '{"input": {"topic": "AI agents"}}'

curl http://localhost:8420/api/runs/<run_id>
curl -X POST http://localhost:8420/api/runs/<run_id>/pause
curl -X PATCH http://localhost:8420/api/runs/<run_id>/tasks/research \
  -H 'Content-Type: application/json' \
  -d '{"permissions": {"bash": "allow"}}'
curl -X POST http://localhost:8420/api/runs/<run_id>/resume
```

## Frontend (Web UI)

The frontend is a **separate service** in `web/frontend/`. It communicates with the backend only through the API. No proxy. No shared process.

```bash
# Terminal 1: start the backend
agentpipe serve --port 8420

# Terminal 2: start the frontend
cd web/frontend
npm install                                        # first time only
npm start                                          # http://0.0.0.0:3000
```

### Configure Backend URL

Edit `web/frontend/.env`:

```
REACT_APP_API_URL=http://localhost:8420
```

Or as environment variable:

```bash
REACT_APP_API_URL=http://192.168.1.100:9000 npm start
```

For production, set the URL before building:

```bash
REACT_APP_API_URL=http://api.example.com:8420 npm run build
```

Serve the built files with any static file server:

```bash
cd web/frontend/build
python -m http.server 3000
```

### What the UI does

| Action | How |
|--------|-----|
| View DAG | Select a pipeline — nodes and edges render automatically |
| Run pipeline | Click **Run**, enter JSON input, watch nodes turn blue → green |
| Pause | Click **Pause** — agents stop between iterations |
| Resume | Click **Resume** — agents continue autonomously |
| Edit task mid-run | Click a node → change goal/permissions/prompt → **Apply** |
| View details | Click any node to see model, permissions, iteration, duration |

## Architecture

```
src/agentpipe/
├── common/         # Shared data types (Message, ToolCall, ToolDefinition) — no dependencies
├── core/           # Task, Pipeline, Permissions, Condition, Constraint — depends on common/
├── tools/          # Tool ABC + 10 built-in tools + registry — depends on common/
├── models/         # ModelProvider + adapters (OpenAI, Anthropic, Ollama, HTTP) — depends on common/
├── execution/      # Agent loop, DAG engine, recovery, conversation window — depends on all above
├── storage/        # YAML definitions + SQLite history — standalone
├── loader/         # YAML/JSON pipeline loaders — depends on core/
├── web/            # REST API server (Starlette) — standalone, depends on execution/
└── cli/            # CLI commands — top level

web/frontend/       # Standalone React app (connects to any API server)
```

Each layer only depends on layers below it. Any module can be imported and used independently.

## CLI

```bash
agentpipe run <pipeline.yaml> [--models <models.yaml>] --input <json> [--watch] [--interactive]
agentpipe pipelines validate <file>
agentpipe pipelines dag <file> [--mermaid]
agentpipe status list [agent] [--limit N]
agentpipe status show <run-id>
agentpipe serve [--host HOST] [--port PORT]    # defaults from AGENTPIPE_HOST/AGENTPIPE_PORT env vars
```

## Development

```bash
conda activate agentpipe

ruff check src/ tests/ --fix    # lint + auto-fix
ruff format src/ tests/         # format
pytest -v                       # run tests
agentpipe serve                 # start API server
agentpipe pipelines validate examples/01-hello-world.yaml   # validate a pipeline
```

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

Scopes (optional): `core`, `execution`, `tools`, `models`, `common`, `cli`, `web`, `docs`

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## Docker

```bash
cp .env.example .env       # edit with your API keys
docker compose up           # backend :8420 + frontend :3000
```

### Configuration

One `.env` file. Same vars for local and Docker:

```bash
AGENTPIPE_HOST=0.0.0.0         # backend bind host
AGENTPIPE_PORT=8420             # backend port (mapped to host)
AGENTPIPE_LOG_LEVEL=info
REACT_APP_API_URL=http://localhost:8420   # frontend → backend URL
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://host.docker.internal:11434   # Ollama on host machine
```

All defaults are defined in `src/agentpipe/config.py`. No values are hardcoded in the Dockerfile or application code.

**Without Docker** — the app reads env vars directly from your shell or `.env` file.
**With Docker** — docker-compose passes `.env` into the container. The app inside reads the same vars.

### Custom port

```bash
# In .env:
AGENTPIPE_PORT=9000
REACT_APP_API_URL=http://localhost:9000

docker compose up    # backend on :9000, frontend on :3000
```

## Requirements

All managed by `environment.yml` + `pyproject.toml`:

- **Conda**: Python 3.11, Node.js 20
- **Python**: pydantic, httpx, pyyaml, starlette, uvicorn, ruff, pytest, pre-commit, commitizen
- **Node**: React, React Flow (installed via `npm install` in `web/frontend/`)

## Acknowledgements

AgentPipe is inspired by and references patterns from several open-source projects:

| Project | What we reference | How it's used in AgentPipe |
|---------|-------------------|---------------------------|
| [Apache Airflow](https://airflow.apache.org/) | DAG-based task orchestration, `depends_on` dependency model | Pipeline structure: tasks as DAG nodes, topological execution, parallel branches |
| [OpenCode](https://opencode.ai/) ([docs](https://opencode.ai/docs/permissions)) | Permission system (`allow`/`ask`/`deny`), tool model, built-in tools | Permission format: `"*": deny`, per-tool rules, granular wildcard patterns. Tool names: `read`, `edit`, `bash`, `glob`, `grep`, `list`, `webfetch` |
| [Codex CLI](https://github.com/openai/codex) | Agent tool system, shell execution, file operations | Tool interface design: tools as typed functions with schema definitions |
| [karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (CLAUDE.md) | Four principles: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution | Skill file pattern: `examples/prompts/*.md` follow the Principles + Loop + Success Criteria structure |
| [autoresearch](https://github.com/karpathy/autoresearch) (program.md) | Autonomous agent loop: propose → experiment → measure → keep/discard → repeat | Agent loop design: think-act-observe cycle. Example: `examples/prompts/autonomous-researcher.md` |
| [React Flow](https://reactflow.dev/) | Node-based canvas UI (same library behind [n8n](https://n8n.io/)) | Web UI: DAG visualization with draggable nodes, status colors, edge animations |

No code is copied from these projects. AgentPipe implements its own versions inspired by their patterns and documentation.

## License

Apache-2.0

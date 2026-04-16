# Tutorial: Build and Run Your First Agent Pipeline

This tutorial walks you through configuring, running, and verifying AgentPipe from scratch. By the end you will have run five different pipelines that test every major feature of the system.

## Prerequisites

- Conda (Miniconda or Anaconda)
- An API key for at least one model provider (OpenAI, Anthropic, or a local Ollama instance)

## 1. Install AgentPipe

```bash
git clone https://github.com/your-org/your-own-agents.git
cd your-own-agents

# Create conda environment
conda env create -f environment.yml
conda activate agentpipe

# Install hooks + build frontend
make post-setup
```

Verify:

```bash
agentpipe --version
# agentpipe 0.1.0

make check
# All checks passed.
```

## 2. Configure Your Model

You need to register at least one model. Pick the provider you have access to.

### Option A: OpenAI

```bash
export OPENAI_API_KEY="sk-..."

agentpipe models register default \
  --provider openai \
  --connection '{"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"}'
```

### Option B: Anthropic

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

agentpipe models register default \
  --provider anthropic \
  --connection '{"api_key_env": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-20250514"}'
```

### Option C: Ollama (local, free)

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3

agentpipe models register default \
  --provider ollama \
  --connection '{"base_url": "http://localhost:11434", "model": "llama3"}'
```

Verify the model is registered:

```bash
agentpipe models list
# Models:
#   - default (openai) [active] capabilities: none
```

## 3. Tutorial 1: Hello World (Single Agent)

The simplest pipeline — one agent with one goal.

**View the pipeline:**

```bash
agentpipe pipelines dag examples/01-hello-world.yaml
```

**Create and run:**

```bash
agentpipe agents create hello --pipeline examples/01-hello-world.yaml
agentpipe run hello --input '{"topic": "quantum computing"}'
```

**What to verify:**
- The agent produces a greeting about quantum computing
- Execution completes without errors

## 4. Tutorial 2: Sequential Pipeline (Dependencies)

Two agents in sequence. The first agent researches a topic, the second summarizes it. The output of agent 1 flows as input to agent 2.

**View the DAG:**

```bash
agentpipe pipelines dag examples/02-sequential-pipeline.yaml
```

You should see:

```
  [ research (default) ]
      |
    research --> summarize
      |
  [ summarize (default) ]
```

**Create and run:**

```bash
agentpipe agents create researcher --pipeline examples/02-sequential-pipeline.yaml
agentpipe run researcher --input '{"topic": "benefits of open source software"}' --watch
```

**What to verify:**
- `research` runs first, uses shell tool (`echo`)
- `summarize` runs after, receives research output as input
- `--watch` shows real-time status updates:
  ```
  [research] Running... (model: default)
  [research] Completed (2.1s)
  [summarize] Running... (model: default)
  [summarize] Completed (1.3s)
  ```

## 5. Tutorial 3: Parallel Pipeline (Fan-out / Fan-in)

Four agents: gather → (analyze-code, analyze-docs) in parallel → report.

**View the DAG:**

```bash
agentpipe pipelines dag examples/03-parallel-pipeline.yaml
```

You should see two tasks at the same level (parallel):

```
  [ gather (default) ]
      |
    gather --> analyze-code
    gather --> analyze-docs
      |
  [ analyze-code (default) ]    [ analyze-docs (default) ]
      |
    analyze-code --> report
    analyze-docs --> report
      |
  [ report (default) ]
```

**Create and run:**

```bash
agentpipe agents create parallel-demo --pipeline examples/03-parallel-pipeline.yaml
agentpipe run parallel-demo --input '{"project": "agentpipe"}' --watch
```

**What to verify:**
- `gather` runs first
- `analyze-code` and `analyze-docs` run at the same time (parallel)
- `report` waits for both to finish, then runs
- The fan-out / fan-in pattern works like Airflow

## 6. Tutorial 4: Permission Control

Three agents with different permission levels. The reviewer can only read files. The fixer can read + write. The verifier can read + run shell commands.

**View the DAG:**

```bash
agentpipe pipelines dag examples/04-permissions-demo.yaml
```

**Create and run:**

```bash
agentpipe agents create perms-demo --pipeline examples/04-permissions-demo.yaml
agentpipe run perms-demo --input '{"file": "examples/04-permissions-demo.yaml"}' --watch
```

**What to verify:**
- `reviewer` reads the file but cannot write or run commands
- `fixer` writes to `output/fix-report.txt` (project-local)
- `verifier` reads the file and runs `cat` via shell
- If any agent tries to use a tool outside its permissions, it gets an error message

## 7. Tutorial 5: Conditional Routing

The evaluator scores the input text. If the score is above 0.7, execution routes to `publish`. Otherwise, it routes to `improve`.

**View the DAG:**

```bash
agentpipe pipelines dag examples/05-conditional-routing.yaml
```

You should see the condition labels on the edges:

```
  [ evaluate (default) ]
      |
    evaluate --> improve  [if quality_score <= 0.7]
    evaluate --> publish  [if quality_score > 0.7]
      |
  [ improve (default) ]    [ publish (default) ]
```

**Create and run:**

```bash
agentpipe agents create quality-gate --pipeline examples/05-conditional-routing.yaml
agentpipe run quality-gate --input '{"text": "AgentPipe is an Airflow-inspired agent framework."}' --watch
```

**What to verify:**
- `evaluate` runs and produces a quality_score
- If score > 0.7: `publish` runs, `improve` is skipped
- If score <= 0.7: `improve` runs, `publish` is skipped
- Only one branch executes (the other is skipped)

## 8. Tutorial 6: Multi-Model Pipeline

Different agents use different models. This requires registering two models.

**Setup (requires two API keys):**

```bash
agentpipe models register gpt-4o \
  --provider openai \
  --connection '{"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o"}'

agentpipe models register claude \
  --provider anthropic \
  --connection '{"api_key_env": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-20250514"}'
```

**Create and run:**

```bash
agentpipe agents create multi-model --pipeline examples/06-multi-model.yaml
agentpipe run multi-model --input '{"task": "write a sorting algorithm"}' --watch
```

**What to verify:**
- `plan` uses gpt-4o
- `implement` uses claude (falls back to gpt-4o if claude fails)
- `test` uses gpt-4o
- The implementation file is created and the test actually runs it

## 9. Tutorial 7: Configuration from Files

Goals, prompts, and permissions can all live in separate files. This keeps pipelines clean and configs reusable.

**View the file layout:**

```bash
ls examples/goals/        # .md files for goals
ls examples/prompts/      # .md files for system prompts
ls examples/permissions/  # .yaml files for permissions
cat examples/07-file-config.yaml   # pipeline that references all three
```

**Three fields support file paths:**

```yaml
tasks:
  - name: researcher
    goal: examples/goals/research.md               # .md or .txt
    system_prompt: examples/prompts/researcher.md   # .md, .txt, or .prompt
    permissions: examples/permissions/read-only.yaml # .yaml or .json
    models: [gpt-4o, claude, local-llama]
```

If the value is a path to an existing file with a supported extension, its contents are loaded. Otherwise the value is used as-is (inline).

**Reusable presets:**

```
examples/
├── goals/           research.md, write-report.md
├── prompts/         code-reviewer.md, code-fixer.md, researcher.md, report-writer.md, tester.md
└── permissions/     read-only.yaml, read-write.yaml, reviewer.yaml, developer.yaml, tester.yaml, full-access.yaml
```

Reference them from any pipeline — share the same prompt or permission across multiple tasks or pipelines.

**Create and run (requires gpt-4o, claude, and local-llama registered):**

```bash
agentpipe agents create file-config --pipeline examples/07-file-config.yaml
agentpipe run file-config --input '{"topic": "AI agents"}' --watch
```

**What to verify:**
- Goals are loaded from `.md` files
- System prompts are loaded from `.md` files
- Permissions are loaded from `.yaml` files
- Models list determines primary + fallback order

## 10. Using the Web UI

Start the web server:

```bash
# Build frontend (first time only)
cd web/frontend && npm install && npm run build && cd ../..

# Start server
agentpipe serve
```

Open `http://localhost:8420` in your browser.

**What to try:**
1. Select a pipeline from the dropdown (e.g., `researcher`)
2. Enter JSON input and click **Run**
3. Watch nodes change color in real time (grey → blue → green)
4. Click a node to see details (goal, model, permissions)
5. While running, click **Pause**, edit a task's permissions or goal, then **Resume**

## 10. Using the REST API

All UI actions are available as API calls:

```bash
# List pipelines
curl http://localhost:8420/api/pipelines

# Get DAG structure
curl http://localhost:8420/api/pipelines/researcher

# Run a pipeline
curl -X POST http://localhost:8420/api/pipelines/researcher/run \
  -H 'Content-Type: application/json' \
  -d '{"input": {"topic": "AI agents"}}'

# Check run status
curl http://localhost:8420/api/runs/<run_id>

# Pause a run
curl -X POST http://localhost:8420/api/runs/<run_id>/pause

# Update a task mid-run (change permissions)
curl -X PATCH http://localhost:8420/api/runs/<run_id>/tasks/research \
  -H 'Content-Type: application/json' \
  -d '{"permissions": {"bash": "allow"}}'

# Resume
curl -X POST http://localhost:8420/api/runs/<run_id>/resume
```

## 11. Using the Python API

```python
import asyncio
from agentpipe import Agent, Pipeline, TaskDefinition, Permissions, ModelConfig

pipeline = Pipeline(
    name="my-pipeline",
    tasks=[
        TaskDefinition(
            name="research",
            goal="examples/goals/research.md",
            system_prompt="examples/prompts/researcher.md",
            primary_model="default",
            permissions=Permissions({"*": "deny", "read": "allow", "bash": "allow"}),
            max_iterations=5,
        ),
        TaskDefinition(
            name="summarize",
            goal="examples/goals/summarize.md",
            primary_model="default",
            # no permissions override → default read-only
            depends_on="research",
            max_iterations=3,
        ),
    ],
)

agent = Agent(
    name="my-agent",
    pipeline=pipeline,
    model_configs=[
        ModelConfig(
            name="default",
            provider="openai",  # or "anthropic" or "ollama"
            connection={"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"},
        ),
    ],
)

result = asyncio.run(agent.execute({"topic": "AI agents"}))
print(result)
```

## 12. Interactive Mode (Interrupt and Modify)

Run with `--interactive` to control the pipeline while it runs:

```bash
agentpipe run researcher --input '{"topic": "AI"}' --interactive
```

Press **Ctrl+C** at any time to pause:

```
--- PAUSED at [research] iteration 2 ---
  Goal: Research the given topic...
  Model: default
  Permissions: read=allow write=deny delete=deny shell=allow web=deny

Commands:
  r / resume        - Continue autonomous execution
  p <perm> <on|off> - Toggle permission (e.g. 'p bash on')
  g <new goal>      - Update the goal
  s <new prompt>    - Update the system prompt
  q / quit          - Abort the pipeline

> p web_fetch on
  web_fetch = True
> g Research the topic using web search and produce findings
  Goal updated
> r
```

After you type `r`, the pipeline resumes autonomously with the updated settings.

## Summary: What Each Tutorial Tests

| Tutorial | Feature Tested |
|----------|---------------|
| 1. Hello World | Single agent, basic execution, submit_result |
| 2. Sequential | `depends_on` (Airflow-style), data flow between agents |
| 3. Parallel | Fan-out / fan-in, concurrent execution |
| 4. Permissions | `allow` / `deny` per tool, permission enforcement |
| 5. Conditional | Edge conditions, branch routing, task skipping |
| 6. Multi-Model | Different models per task, fallback models |
| 7. File Config | Goal from `.md` file, permissions from `.yaml` file, `models` list |
| 8. Web UI | DAG visualization, live status, pause/resume, task editing |
| 9. REST API | Programmatic control |
| 10. Python API | Library usage |
| 11. Interactive | Ctrl+C interrupt, mid-run permission/goal changes |

## Token and Context Control

For long-running agents, control token usage and conversation size:

```yaml
tasks:
  - name: researcher
    goal: goals/research.md
    primary_model: default
    max_iterations: 20       # max think-act-observe cycles
    max_tokens: 50000        # stop after spending 50K tokens total
    context_window: 8000     # trim conversation to fit 8K tokens
```

- `max_tokens` — total token budget. The agent stops when this is exceeded.
- `context_window` — old messages are automatically trimmed to keep the conversation within this limit. System prompt is always preserved.

## Agent Isolation

Each task in a pipeline runs in complete isolation:

- Each task creates its own model provider (own HTTP session, own connection)
- No conversation history is shared between agents
- Parallel tasks never interfere with each other
- Data flows only through the DAG (upstream output → downstream input)

## Troubleshooting

**"Model provider not found"** — Register a model first:
```bash
agentpipe models register default --provider openai --connection '{"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"}'
```

**"API key not found"** — Set your environment variable:
```bash
export OPENAI_API_KEY="sk-..."
```

**Agent runs but produces empty output** — Test the model directly:
```bash
agentpipe models test default --prompt "Say hello"
```

**Task keeps looping** — Set `max_iterations` or `max_tokens` to limit the agent. Make the goal more specific so the agent knows when to call `submit_result`.

**Permission denied for a tool** — Set the tool to `allow` in permissions:
```yaml
permissions:
  bash: allow
```

**Conversation too large** — Set `context_window` to automatically trim old messages:
```yaml
context_window: 8000
```

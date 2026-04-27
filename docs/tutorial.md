# Tutorial

## 1. Install

```bash
conda env create -f environment.yml
conda activate agentpipe
```

## 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```bash
AGENTPIPE_MODELS=my_models.yaml
AGENTPIPE_RULES=examples/prompts/agent_rules.md
AGENTPIPE_PERMISSIONS=examples/permissions/default.yaml
AGENTPIPE_LOGS_DIR=logs
```

## 3. Set Up Models

Create `my_models.yaml` with your provider's connection details:

```yaml
models:
  - name: default
    provider: microsoft-foundry-anthropic
    connection:
      api_key: your-api-key
      base_url: https://your-endpoint/anthropic/v1
      model: claude-haiku-4-5
```

## 4. Run a Pipeline (CLI)

```bash
agentpipe run examples/01-hello-world.yaml --watch
```

You'll see:
- Pipeline DAG (task order and dependencies)
- Streaming model output as the agent thinks
- Tool calls as they happen
- Task output when each agent completes
- Conversation logs saved to `logs/`

## 5. Run with Web UI

```bash
# Terminal 1: backend
agentpipe serve

# Terminal 2: frontend
cd web/frontend && bun install && bun start
```

Open http://localhost:3000:
- Select a pipeline → click **Run**
- Watch nodes change color in real time
- Click any node to see its conversation log
- Pause / Resume / Edit task mid-run

## 6. Run with Docker

```bash
docker compose up
```

## 7. Run via API

```bash
# Run
curl -X POST http://localhost:8420/api/pipelines/01-hello-world/run -d '{}'

# Status
curl http://localhost:8420/api/runs/<run_id>

# Task logs
curl http://localhost:8420/api/runs/<run_id>/tasks/<task_name>/logs
```

## 8. Create Your Own Pipeline

### Define the goal (what the agent should do)

```markdown
# goals/review.md
Review the code for bugs. Submit findings as JSON.
```

### Define the prompt (how the agent should behave)

```markdown
# prompts/reviewer.md
## Principles
- Think before acting
- Be specific with file paths and line numbers

## Success Criteria
Done when all files reviewed and results submitted.
```

### Define permissions (what the agent can do)

```yaml
# permissions/read-only.yaml
"*": deny
read: allow
glob: allow
grep: allow
```

### Create the pipeline

```yaml
# my-pipeline.yaml
name: code-review
models: my_models.yaml

tasks:
  - name: review
    goal: goals/review.md
    prompts:
      - examples/prompts/agent_rules.md
      - prompts/reviewer.md
    primary_model: default
    permissions: permissions/read-only.yaml
    max_iterations: 10
```

### Run it

```bash
agentpipe run my-pipeline.yaml --watch
```

## 9. Multi-Task Pipeline with Dependencies

```yaml
name: review-and-fix
models: my_models.yaml

tasks:
  - name: review
    goal: goals/review.md
    prompts: [examples/prompts/agent_rules.md, prompts/reviewer.md]
    primary_model: default
    permissions: permissions/read-only.yaml
    max_iterations: 10

  - name: fix
    goal: goals/fix.md
    prompts: [examples/prompts/agent_rules.md, prompts/fixer.md]
    primary_model: default
    permissions: permissions/developer.yaml
    depends_on: review
    max_iterations: 15
```

The `fix` agent receives `review`'s output automatically:

```python
# fix agent's input:
{"review": {"findings": [...], "summary": "..."}}
```

## 10. Conditional Routing

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

## 11. Debug with Conversation Logs

Every task's full conversation is saved to `AGENTPIPE_LOGS_DIR`:

```bash
cat logs/review.json | python -m json.tool
```

Contains: system prompt, goal, every model response, every tool call and result, final output.

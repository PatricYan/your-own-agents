# Contributing

## Setup

```bash
git clone https://github.com/your-org/your-own-agents.git
cd your-own-agents

# Create isolated conda environment
conda env create -f environment.yml
conda activate agentpipe

# Install git hooks + build frontend
make post-setup

# Verify
make check
```

This gives you:
- Python 3.11 + Node.js 20 in an isolated conda env (`agentpipe`)
- All Python deps (pydantic, httpx, ruff, pytest, starlette, etc.)
- Three commit gates enforced by pre-commit hooks (see below)
- Built React frontend for the web UI

## Commit Gates

Every `git commit` must pass three gates. They run automatically via pre-commit hooks — no commit goes through unless all three pass.

### Gate 1: Code format check

Ruff lint and ruff format run on all staged Python files. Lint auto-fixes what it can. If unfixable issues remain or formatting is wrong, the commit is blocked.

### Gate 2: Unit tests must pass

`pytest tests/ --tb=short -q` runs on every commit. If any test fails, the commit is blocked. You cannot commit broken code.

### Gate 3: Commit message format

The commit message must follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Bad messages are rejected:

```
$ git commit -m "fixed stuff"
gate: conventional commit msg ... Failed
```

Good messages pass:

```
$ git commit -m "feat(core): add agent pipeline framework"
gate: conventional commit msg ... Passed
```

## Commit Messages

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no logic change |
| `refactor` | Code restructuring, no behavior change |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests |
| `build` | Build system, dependencies |
| `ci` | CI/CD configuration |
| `chore` | Maintenance, tooling |

**Scope** (optional): the module affected — `core`, `execution`, `tools`, `models`, `cli`, `web`, `docs`

**Examples:**

```
feat(tools): add web_search tool
fix(execution): handle timeout in agent loop
docs: update tutorial with multi-model example
refactor(core): simplify permission validation
test(web): add API endpoint tests
build: add pre-commit hooks
```

**Breaking changes** — add `!` after type or `BREAKING CHANGE:` in footer:

```
feat(core)!: change models field from string to list
```

Use `cz commit` for an interactive commit wizard, or write the message directly.

## Branch Naming

```
<type>/<short-description>

feat/add-web-search-tool
fix/agent-loop-timeout
docs/update-tutorial
```

## Workflow

```bash
# 0. Activate env
conda activate agentpipe

# 1. Branch
git checkout -b feat/my-feature

# 2. Code
# ... make changes ...

# 3. Stage
git add -A

# 4. Commit (hooks run automatically)
git commit -m "feat(core): add my feature"

# 5. Push
git push -u origin feat/my-feature

# 6. Open PR on GitHub
```

The three commit gates run automatically on `git commit`:

1. **Code format** — ruff lint + format (auto-fixes, blocks if unfixable)
2. **Unit tests** — pytest must pass (blocks if any test fails)
3. **Commit message** — conventional commits format required

Plus file hygiene: trailing whitespace, YAML/JSON syntax, merge conflicts, large files (>500KB).

If any gate fails, the commit is rejected. Fix the issue and commit again.

## Code Style

- Python 3.11+
- Ruff for lint and format (line length 100)
- Type hints on all public functions
- Pydantic models for data structures
- `async def` for all I/O operations

All enforced by pre-commit. No manual formatting needed.

## Pull Requests

Every PR must:

- [ ] Follow the PR template (auto-loaded by GitHub)
- [ ] Have conventional commit messages
- [ ] Pass `ruff check src/` and `ruff format --check src/ tests/`
- [ ] Pass `pytest`
- [ ] Validate examples: `agentpipe pipelines validate examples/*.yaml`
- [ ] Update docs if behavior changes

One PR = one logical change. Keep PRs focused.

## Project Layout

```
src/agentpipe/
  core/            task.py pipeline.py agent.py condition.py constraint.py visualize.py
  execution/       agent_loop.py conversation.py engine.py runner.py recovery.py state.py
  models/          provider.py registry.py adapters/{openai,anthropic,ollama,http}.py
  tools/           base.py registry.py builtin/{10 tools}
  storage/         definitions.py history.py
  loader/          yaml_loader.py json_loader.py
  web/             api.py state.py serve.py
  cli/             main.py run.py models.py pipelines.py status.py
web/frontend/      React + React Flow
examples/          Pipeline YAML files + goals/ + permissions/
docs/              Tutorial and guides
tests/             Test suite
```

## Extending

### Add a tool

1. `src/agentpipe/tools/builtin/my_tool.py` — implement `Tool` ABC
2. `src/agentpipe/tools/registry.py` — register in `create_default_registry()`
3. `src/agentpipe/core/task.py` — add permission field + `_TOOL_MAP` entry
4. Test it

### Add a model adapter

1. `src/agentpipe/models/adapters/my_provider.py` — implement `ModelProvider.chat()`
2. `src/agentpipe/models/adapters/__init__.py` — add dispatch case
3. Test it

### Add a CLI command

1. `src/agentpipe/cli/my_command.py` — handler function
2. `src/agentpipe/cli/main.py` — add subparser + dispatch
3. Test it

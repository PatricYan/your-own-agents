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

# Verify everything works
make check
```

This gives you:
- Python 3.11 + Node.js 20 in an isolated conda env (`agentpipe`)
- All Python deps installed via `pip install -e ".[dev]"` inside the conda env
- Pre-commit hooks installed (5 gates enforced on every commit)
- Built React frontend for the web UI

## Commit Gates

Every `git commit` must pass **all** of the following. They run automatically via pre-commit hooks — no commit goes through unless every gate passes.

### Gate 1: Ruff lint

Runs `ruff check --fix` on all staged Python files. Auto-fixes what it can. If unfixable issues remain, the commit is blocked.

**Ruff rules enabled** (configured in `pyproject.toml`):

| Rule set | What it checks |
|----------|---------------|
| `E`, `W` | pycodestyle errors and warnings |
| `F` | pyflakes (unused imports, undefined names) |
| `I` | isort (import order) |
| `N` | pep8-naming (function/class naming) |
| `UP` | pyupgrade (Python 3.11+ syntax) |
| `B` | flake8-bugbear (common bugs) |
| `SIM` | flake8-simplify (code simplification) |

Line length: **100 characters**.

### Gate 2: Ruff format

Runs `ruff format` on all staged Python files. Enforces consistent formatting (double quotes, 4-space indent, auto line endings).

### Gate 3: File hygiene

| Check | What it does |
|-------|-------------|
| Trailing whitespace | Removes trailing spaces from all files |
| End of file | Ensures files end with a newline |
| YAML syntax | Validates all `.yaml`/`.yml` files |
| JSON syntax | Validates all `.json` files |
| Merge conflicts | Blocks commits containing conflict markers |
| Debug statements | Blocks `print()`, `breakpoint()`, `pdb` in Python |

### Gate 4: Unit tests

Runs `pytest tests/ --tb=short -q`. If any test fails, the commit is blocked. You cannot commit broken code.

### Gate 5: Commit message format

The commit message must follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Enforced by commitizen.

## Commit Messages

Format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

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

### Scopes (optional)

The module affected: `core`, `execution`, `tools`, `models`, `schema`, `cli`, `web`, `docs`

### Examples

```
feat(tools): add web_search tool
fix(execution): handle timeout in agent loop
docs: update tutorial with multi-model example
refactor(core): simplify permission validation
test(schema): add conversation serialization tests
build: update conda environment
chore: remove dead code
```

### Breaking changes

Add `!` after type or `BREAKING CHANGE:` in footer:

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

# 3. Verify locally before committing
make lint                    # ruff check + fix
make format                  # ruff format
make test                    # pytest

# 4. Stage
git add -A

# 5. Commit (all 5 gates run automatically)
git commit -m "feat(core): add my feature"

# 6. Push
git push -u origin feat/my-feature

# 7. Open PR on GitHub
```

If any gate fails, the commit is rejected. Fix the issue and commit again.

## Code Style

- Python 3.11+
- Ruff for lint and format (line length 100, double quotes, 4-space indent)
- Type hints on all public functions
- Pydantic models for data structures
- `async def` for all I/O operations
- Import shared types from `agentpipe.schema` (not from `execution/` or `tools/`)

All enforced by pre-commit hooks. No manual formatting needed.

## Pull Requests

Every PR must:

- [ ] Follow the [PR template](.github/pull_request_template.md)
- [ ] Have all commits following [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format
- [ ] Pass `ruff check src/ tests/` (no lint errors)
- [ ] Pass `ruff format --check src/ tests/` (correctly formatted)
- [ ] Pass `pytest` (all tests green)
- [ ] Validate examples: `agentpipe pipelines validate examples/*.yaml`
- [ ] New code has tests
- [ ] Documentation updated if behavior changes

One PR = one logical change. Keep PRs focused.

## Project Layout

```
src/agentpipe/
  schema/          Shared types: Message, ToolCall, ToolDefinition (no deps)
  core/            task.py pipeline.py agent.py condition.py constraint.py visualize.py
  execution/       agent_loop.py engine.py runner.py recovery.py state.py
  models/          provider.py http_session.py registry.py adapters/{openai,anthropic,ollama,http}.py
  tools/           base.py registry.py builtin/{10 tools}
  storage/         definitions.py history.py
  loader/          yaml_loader.py json_loader.py
  web/             api.py state.py serve.py
  cli/             main.py run.py models.py pipelines.py status.py
web/frontend/      React + React Flow
examples/          Pipeline YAML + goals/ + prompts/ + permissions/
docs/              Tutorial
tests/             214 tests across 13 files
```

**Dependency layers** (each only depends on layers below):

```
Layer 0: schema/              ← no dependencies
Layer 1: tools/, models/, storage/  ← depend on schema/ only
Layer 2: core/, loader/       ← depend on schema/ + core/
Layer 3: execution/           ← depends on all above
Layer 4: cli/, web/           ← top-level entry points
```

## Extending

### Add a tool

1. `src/agentpipe/tools/builtin/my_tool.py` — implement `Tool` ABC
2. `src/agentpipe/tools/registry.py` — register in `create_default_registry()`
3. `src/agentpipe/core/task.py` — add `_normalize()` mapping in `Permissions`
4. Test in `tests/test_tools.py`

### Add a model adapter

1. `src/agentpipe/models/adapters/my_provider.py` — implement `ModelProvider.chat()`, use `HttpSession`
2. `src/agentpipe/models/adapters/__init__.py` — add dispatch case
3. Import from `agentpipe.schema` (not from `execution/` or `tools/`)
4. Test in `tests/test_model_contract.py`

### Add a CLI command

1. `src/agentpipe/cli/my_command.py` — handler function
2. `src/agentpipe/cli/main.py` — add subparser + dispatch
3. Test in `tests/test_tutorial.py` (CLI section)

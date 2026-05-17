# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
pip install -e .              # install in editable mode
python -m pytest test/ -v     # run all tests
python -m pytest test/test_cli.py::ClassName::test_name -v  # run single test
python src/main.py            # run directly without install
```

No separate lint or build steps. Python >=3.9, only external dependency is `pyyaml`.

## Architecture

t-loop is a CLI tool that automates Claude Code tasks defined in `~/.tloop/tasks.yaml`. All source modules live flat under `src/` (no sub-package).

**Entry point:** `src/main.py` → `src/cli.py:main()`

**Module dependency graph:**
```
main.py → cli.py → git_ops.py → claude_runner.py
```

- **cli.py** — CLI parsing, task loop, state management, archiving. Runtime paths (`TLOOP_HOME`, `TASKS_FILE`, `STATE_FILE`, `LOGS_DIR`, `ARCHIVE_DIR`) are module-level constants pointing to `~/.tloop/`.
- **git_ops.py** — Pre-task git safety: auto-commit dirty working trees (via `claude` CLI), branch creation with collision-safe naming (`feature-YYYYMMDD-NNN`).
- **claude_runner.py** — Wrapper around `claude -p --dangerously-skip-permissions` with retry loop and optional verification function.

**Key flow per task:**
1. `cli.run_task()` → `git_ops.ensure_clean_git()` (auto-commit dirty state) → `git_ops.create_task_branch()` → `subprocess.Popen(["cybervisor", "run", prompt])`
2. After the task loop, `archive_completed_tasks()` moves done tasks to `~/.tloop/archive/`, resets state, and removes them from `tasks.yaml`.

**Task configuration** (`~/.tloop/tasks.yaml`):
- `prompt` (inline) or `prompt_file` (resolved: absolute → `TLOOP_HOME`-relative → task-dir-relative)
- `branch`: `true` = auto `feature-YYYYMMDD-NNN`, `"custom/name"` = use or append suffix, `false` = skip

**Testing:** Tests patch module-level path constants (`cli.TLOOP_HOME`, `cli.TASKS_FILE`, etc.) to redirect to temp dirs. Mock targets use the flat module name (e.g., `@patch("git_ops.run_claude")`).

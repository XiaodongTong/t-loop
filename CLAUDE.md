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

t-loop is a CLI tool that automates Claude Code tasks defined in `~/.tloop/tasks.yaml`. Source modules live flat under `src/` with one sub-package `src/runner/`.

**Entry point:** `src/main.py` — argparse router with subcommands `run`, `edit`, `migrate`, `archive`.

**Module dependency graph:**
```
main.py → cmd_run.py → task.py → git_ops.py → claude_runner.py
                       task.py → runner/cybervisor.py
         cmd_run.py → state.py → config.py
         cmd_edit.py → config.py
         cmd_migrate.py → config.py
         cmd_archive.py → state.py → config.py
```

- **config.py** — Runtime paths (`TLOOP_HOME`, `TASKS_FILE`, `STATE_FILE`, `LOGS_DIR`, `ARCHIVE_DIR`), color constants, `ensure_tloop_home()`, `load_config()`. All other modules access paths via `config.X` references for testability.
- **state.py** — `load_state()`, `save_state()`, `show_status()`, `archive_completed_tasks()`, `show_archives()`.
- **task.py** — `run_task()`, `resolve_prompt_file()`, `expand_dir()`. Uses `CybervisorRunner` from the runner package.
- **cmd_run.py** — `tloop run` subcommand: task loop, status display, archiving.
- **cmd_edit.py** — `tloop edit` subcommand: opens tasks.yaml in `$EDITOR`.
- **cmd_migrate.py** — `tloop migrate` subcommand: migrates old data to `~/.tloop/`.
- **cmd_archive.py** — `tloop archive` subcommand: view archived runs.
- **git_ops.py** — Pre-task git safety: auto-commit dirty working trees (via `claude` CLI), branch creation with collision-safe naming (`feature-YYYYMMDD-NNN`).
- **claude_runner.py** — Wrapper around `claude -p --dangerously-skip-permissions` with retry loop and optional verification function.
- **runner/** — Runner base class (`Runner` ABC) and backends (`CybervisorRunner`, `ClaudeRunner` placeholder).

**Key flow per task:**
1. `task.run_task()` → `git_ops.ensure_clean_git()` → `git_ops.create_task_branch()` → `CybervisorRunner.run()`
2. After the task loop, `archive_completed_tasks()` moves done tasks to `~/.tloop/archive/`, resets state, and removes them from `tasks.yaml`.

**Task configuration** (`~/.tloop/tasks.yaml`):
- `prompt` (inline) or `prompt_file` (resolved: absolute → `TLOOP_HOME`-relative → task-dir-relative)
- `branch`: `true` = auto `feature-YYYYMMDD-NNN`, `"custom/name"` = use or append suffix, `false` = skip

**Testing:** Tests patch `config.TLOOP_HOME`, `config.TASKS_FILE`, etc. to redirect to temp dirs. All modules use `config.X` references, so patching `config` propagates everywhere.

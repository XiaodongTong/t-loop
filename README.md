# t-loop

Automated Claude Code task runner. Define tasks in YAML, let t-loop run them sequentially with automatic git safety.

## Install

```bash
pip install -e .
```

Requires Python >=3.9. Only external dependency: `pyyaml`.

## Quick Start

```bash
# First run creates ~/.tloop/tasks.yaml with a sample config
t-loop

# Edit tasks and run
vim ~/.tloop/tasks.yaml
t-loop
```

## Task Configuration

Edit `~/.tloop/tasks.yaml`:

```yaml
defaults:
  model: opus          # optional, applies to all tasks

tasks:
  - name: My first task
    dir: ~/projects/my-project
    prompt: |
      Describe what Claude should do here.

  - name: Task with prompt file
    dir: ~/projects/my-project
    prompt_file: ./prompts/my-task.md
    branch: feat/login   # custom branch name
```

### Task fields

| Field | Description |
|-------|-------------|
| `name` | Task display name |
| `dir` | Working directory for the task |
| `prompt` | Inline prompt text |
| `prompt_file` | Path to prompt file (resolved: absolute → `~/.tloop/`-relative → task-dir-relative) |
| `model` | Override model for this task |
| `branch` | `true` (auto `feature-YYYYMMDD-NNN`), `"custom/name"`, or `false` (skip branch) |

## Usage

```bash
t-loop                    # run all pending tasks
t-loop --status           # show task status
t-loop --only 2           # run only task #2
t-loop --confirm          # confirm before each task
t-loop -c                 # continue after failures
t-loop --reset            # reset all tasks to pending
t-loop --archive          # list archived runs
t-loop --archive latest   # show most recent archive
t-loop migrate            # migrate old project-local data to ~/.tloop/
```

## How It Works

For each task:

1. **Auto-commit** — If the working directory is dirty, t-loop uses Claude to commit staged changes, then remaining changes. Sensitive files (.env, credentials, etc.) are excluded.
2. **Branch creation** — Creates a task branch (`feature-YYYYMMDD-NNN` by default) to isolate changes.
3. **Task execution** — Runs `cybervisor run <prompt>` in the target directory.
4. **Archiving** — Completed tasks are moved to `~/.tloop/archive/` and removed from `tasks.yaml`.

## File Locations

```
~/.tloop/
├── tasks.yaml      # task definitions
├── state.json      # runtime state (task statuses)
├── logs/           # execution logs
└── archive/        # completed run archives
```

## Development

```bash
pip install -e .
python -m pytest test/ -v
```

## License

MIT

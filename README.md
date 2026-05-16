# t-loop

Automated Claude Code task runner. Define tasks in `tasks.yaml`, let Claude execute them one by one.

## Usage

**1. Edit `tasks.yaml`** to define your tasks:

```yaml
defaults:
  model: opus

tasks:
  - name: Fix login timeout bug
    dir: ~/projects/auth-service
    prompt: |
      Fix the login timeout issue in src/auth.ts.
      The session expires after 5 minutes instead of 30.

  - name: Add pagination to users API
    dir: ~/projects/api-gateway
    prompt: |
      Add cursor-based pagination to GET /users endpoint.
    model: sonnet  # override default model

  - name: Refactor with long prompt
    dir: ~/projects/backend
    prompt_file: ./prompts/refactor.md  # read prompt from file

  - name: Fix auth bug on feature branch
    dir: ~/projects/auth-service
    branch: fix/auth  # create task branch (default: auto-generate)
    prompt: |
      Fix the token refresh logic in src/auth.ts.
```

**2. Run all pending tasks:**

```bash
python3 t-loop.py
```

**3. Other commands:**

```bash
python3 t-loop.py -s              # check status
python3 t-loop.py --only 2        # run only task #2
python3 t-loop.py -i              # confirm before each task
python3 t-loop.py -c              # continue even if a task fails
python3 t-loop.py --reset         # reset all tasks to pending
```

## Task fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | no | Task display name |
| `dir` | no | Project directory (supports `~` and `$VAR`) |
| `prompt` | yes* | Prompt to send to Claude |
| `prompt_file` | yes* | Read prompt from file (alternative to `prompt`) |
| `model` | no | Override Claude model for this task |
| `branch` | no | Branch management (see below) |

\* Either `prompt` or `prompt_file` is required.

### Git Safety Protection

Before each task runs, t-loop performs two safety phases on the target directory:

**Auto-commit**: If the target directory is a Git repo with uncommitted changes, t-loop auto-commits them (staged changes first, then working-directory changes). Commit messages are generated in Chinese conventional-commit format. Sensitive files (`.env`, credentials, secret keys) are detected and unstaged — they remain in your working tree but are not committed. If auto-commit fails to produce a clean working tree, the task is skipped and marked as failed.

**Branch management**: Controlled by the `branch` field per task:

| Value | Behavior |
|-------|----------|
| omitted / `true` | Auto-generate a unique branch: `feature-YYYYMMDD-NNN` |
| `"feat/login"` | Use the specified name; append `-NNN` suffix if it already exists |
| `false` | Skip branch creation; work on the current branch |

If the target directory is not a Git repo, all Git-related steps are skipped and the task runs directly. Detached HEAD state is detected and the task is marked as failed rather than creating a branch.

## How it works

1. Reads `tasks.yaml` and `.tloop-state.json`
2. Finds the next pending task
3. Auto-commits any uncommitted changes in the target directory (Git repos only)
4. Creates a task branch if `branch` is configured (Git repos only)
5. Runs `cybervisor run "<prompt>"` in the task's directory
6. Streams output to terminal and saves to `logs/`
7. Updates state, moves to next task

Completed tasks are skipped on subsequent runs. Use `--reset` to re-run all.

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

\* Either `prompt` or `prompt_file` is required.

## How it works

1. Reads `tasks.yaml` and `.tloop-state.json`
2. Finds the next pending task
3. Runs `claude -p "<prompt>"` in the task's directory
4. Streams output to terminal and saves to `logs/`
5. Updates state, moves to next task

Completed tasks are skipped on subsequent runs. Use `--reset` to re-run all.

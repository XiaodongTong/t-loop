"""t-loop CLI: Automated Claude Code task runner."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from git_ops import ensure_clean_git, create_task_branch

TLOOP_HOME = Path.home() / ".tloop"
TASKS_FILE = TLOOP_HOME / "tasks.yaml"
STATE_FILE = TLOOP_HOME / "state.json"
LOGS_DIR = TLOOP_HOME / "logs"
ARCHIVE_DIR = TLOOP_HOME / "archive"

SAMPLE_TASKS_YAML = """\
# t-loop tasks.yaml
# Define your Claude Code automation tasks here.
#
# Location: ~/.tloop/tasks.yaml
#
# Each task runs "cybervisor run <prompt>" in the specified directory.
# Completed tasks are automatically archived after each run cycle.
# View archives with: t-loop --archive
#
# prompt_file paths resolve in this order:
#   1. Absolute path (after ~ expansion)
#   2. Relative to ~/.tloop/
#   3. Relative to the task's dir

defaults:
  # model: opus

tasks: []
  # - name: My first task
  #   dir: ~/projects/my-project
  #   prompt: |
  #     Describe what Claude should do here.
  #
  # - name: Task with prompt file
  #   dir: ~/projects/my-project
  #   prompt_file: ./prompts/my-task.md
"""

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ensure_tloop_home():
    TLOOP_HOME.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    if not TASKS_FILE.exists():
        TASKS_FILE.write_text(SAMPLE_TASKS_YAML)
        print(f"{GREEN}Created {TASKS_FILE}{RESET}")
        print(f"\nEdit ~/.tloop/tasks.yaml to define your tasks, then run t-loop again.")
        sys.exit(0)


def load_config():
    if not TASKS_FILE.exists():
        print(f"{RED}Error: {TASKS_FILE} not found{RESET}")
        print(f"Run t-loop to initialize, then edit tasks.yaml.")
        sys.exit(1)
    with open(TASKS_FILE) as f:
        return yaml.safe_load(f) or {}


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"tasks": {}, "version": 1}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def expand_dir(d):
    return os.path.expandvars(os.path.expanduser(d))


def get_status_icon(status):
    return {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}.get(
        status, "?"
    )


def show_status(tasks, state):
    if not tasks:
        print("  (no tasks)")
        return
    for i, task in enumerate(tasks):
        name = task.get("name", f"Task {i + 1}")
        ts = state.get("tasks", {}).get(str(i), {})
        status = ts.get("status", "pending")
        icon = get_status_icon(status)
        extra = ""
        if status == "done" and "finished_at" in ts:
            extra = f"  ({ts['finished_at'][:16]})"
        elif status == "failed":
            extra = "  (see logs/)"
        print(f"  {icon}  [{i + 1}] {name}{RESET}  {CYAN}{status}{RESET}{extra}")
    print()


def resolve_prompt_file(prompt_file, dir_path):
    """Resolve prompt_file: ~ expansion, TLOOP_HOME-relative, then dir-relative."""
    pf = Path(prompt_file).expanduser()
    if pf.is_absolute():
        return pf
    candidate = TLOOP_HOME / prompt_file
    if candidate.exists():
        return candidate
    candidate = Path(dir_path) / prompt_file
    if candidate.exists():
        return candidate
    return Path(prompt_file)


def run_task(task, index, state, defaults):
    name = task.get("name", f"Task {index + 1}")
    dir_path = expand_dir(task.get("dir", defaults.get("dir", ".")))
    prompt = task.get("prompt", "")
    prompt_file = task.get("prompt_file")
    model = task.get("model", defaults.get("model"))
    branch_config = task.get("branch", True)

    if not os.path.isdir(dir_path):
        print(f"{RED}  Directory not found: {dir_path}{RESET}")
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": f"Directory not found: {dir_path}",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False

    if prompt_file:
        pf = resolve_prompt_file(prompt_file, dir_path)
        if pf.exists():
            prompt = pf.read_text()
        else:
            print(f"{RED}  Prompt file not found: {prompt_file}{RESET}")
            return False

    if not prompt.strip():
        print(f"{RED}  No prompt defined for task: {name}{RESET}")
        return False

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Task [{index + 1}]: {name}{RESET}")
    print(f"  Directory: {CYAN}{dir_path}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    LOGS_DIR.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    log_file = LOGS_DIR / f"{index + 1:03d}-{safe_name}.log"

    with open(log_file, "w") as log:
        log.write(f"Task: {name}\n")
        log.write(f"Directory: {dir_path}\n")
        log.write("-" * 60 + "\n\n")

    if not ensure_clean_git(dir_path, name, log_file):
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": "Failed to clean working tree via auto-commit",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False

    if not create_task_branch(dir_path, branch_config):
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": "Failed to create task branch",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False

    started = datetime.now().isoformat()
    state.setdefault("tasks", {})[str(index)] = {
        "status": "running",
        "started_at": started,
    }
    save_state(state)

    cmd = ["cybervisor", "run", prompt]
    if model:
        cmd.extend(["--model", model])

    try:
        with open(log_file, "a") as log:
            log.write(f"Started: {started}\n")
            log.write(f"Command: cybervisor run <prompt>\n")
            log.write("-" * 60 + "\n\n")
            log.flush()

            process = subprocess.Popen(
                cmd,
                cwd=dir_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            for line in process.stdout:
                print(line, end="")
                log.write(line)
            log.flush()
            process.wait()

        if process.returncode == 0:
            state["tasks"][str(index)] = {
                "status": "done",
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
            }
            save_state(state)
            print(f"\n{GREEN}✅ Task [{index + 1}] done{RESET}")
        else:
            state["tasks"][str(index)] = {
                "status": "failed",
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
                "returncode": process.returncode,
            }
            save_state(state)
            print(
                f"\n{RED}❌ Task [{index + 1}] failed (exit code: {process.returncode}){RESET}"
            )
            print(f"   Log: {log_file}")
            return False

    except Exception as e:
        state["tasks"][str(index)] = {
            "status": "failed",
            "started_at": started,
            "error": str(e),
        }
        save_state(state)
        print(f"\n{RED}❌ Task [{index + 1}] error: {e}{RESET}")
        return False

    return True


def archive_completed_tasks(config, state):
    tasks = config.get("tasks", [])

    completed = []
    remaining = []
    for i, task in enumerate(tasks):
        ts = state.get("tasks", {}).get(str(i), {})
        status = ts.get("status", "pending")
        if status == "done":
            completed.append({"task": task, "index": i, "result": ts})
        else:
            remaining.append(task)

    if not completed:
        return

    total = len(tasks)
    done_count = len(completed)
    failed_count = sum(
        1 for i in range(total)
        if state.get("tasks", {}).get(str(i), {}).get("status") == "failed"
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_data = {
        "archived_at": datetime.now().isoformat(),
        "run_summary": {
            "total": total,
            "done": done_count,
            "failed": failed_count,
            "pending": total - done_count - failed_count,
        },
        "tasks": completed,
    }

    ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_file = ARCHIVE_DIR / f"run-{timestamp}.yaml"
    with open(archive_file, "w") as f:
        yaml.dump(archive_data, f, default_flow_style=False, allow_unicode=True)

    remaining_config = dict(config)
    remaining_config["tasks"] = remaining
    with open(TASKS_FILE, "w") as f:
        yaml.dump(remaining_config, f, default_flow_style=False, allow_unicode=True)

    save_state({"tasks": {}, "version": 1})

    print(f"\n{GREEN}Archived {done_count} completed task(s) to {archive_file.name}{RESET}")


def run_migrate():
    project_root = Path(__file__).resolve().parent.parent.parent

    old_tasks = project_root / "tasks.yaml"
    old_state = project_root / ".tloop-state.json"
    old_logs = project_root / "logs"

    found = []
    if old_tasks.exists():
        found.append(old_tasks)
    if old_state.exists():
        found.append(old_state)
    if old_logs.exists() and old_logs.is_dir():
        found.append(old_logs)

    if not found:
        print(f"{YELLOW}No old data files found in {project_root}{RESET}")
        print("Nothing to migrate.")
        return

    if TASKS_FILE.exists():
        print(f"{RED}Conflict: {TASKS_FILE} already exists{RESET}")
        print("Resolve the conflict manually before migrating.")
        sys.exit(1)

    TLOOP_HOME.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    if old_tasks.exists():
        shutil.copy2(old_tasks, TASKS_FILE)
        print(f"  Migrated: tasks.yaml → {TASKS_FILE}")

        config = yaml.safe_load(open(old_tasks)) or {}
        for i, task in enumerate(config.get("tasks", [])):
            pf = task.get("prompt_file")
            if pf and not Path(pf).expanduser().is_absolute():
                print(
                    f"  {YELLOW}Warning: task '{task.get('name', f'Task {i + 1}')}' "
                    f"has relative prompt_file '{pf}'{RESET}"
                )
                print(f"    Will resolve from {TLOOP_HOME} first, then the task's dir.")

    if old_state.exists():
        shutil.copy2(old_state, STATE_FILE)
        print(f"  Migrated: .tloop-state.json → {STATE_FILE}")

    if old_logs.exists() and old_logs.is_dir():
        for log_file in old_logs.iterdir():
            if log_file.is_file():
                shutil.copy2(log_file, LOGS_DIR / log_file.name)
        print(f"  Migrated: logs/ → {LOGS_DIR}/")

    print(f"\n{GREEN}Migration complete.{RESET}")
    print(f"Old files still exist in {project_root} — remove them manually when ready.")


def show_archives(latest=False):
    if not ARCHIVE_DIR.exists():
        print("No archive files found.")
        return

    archives = sorted(ARCHIVE_DIR.glob("run-*.yaml"), reverse=True)
    if not archives:
        print("No archive files found.")
        return

    if latest:
        with open(archives[0]) as f:
            data = yaml.safe_load(f)
        print(f"{BOLD}Latest archive: {archives[0].name}{RESET}")
        print(f"  Archived at: {data.get('archived_at', 'unknown')}")
        summary = data.get("run_summary", {})
        print(
            f"  Total: {summary.get('total', 0)}, "
            f"Done: {summary.get('done', 0)}, "
            f"Failed: {summary.get('failed', 0)}, "
            f"Pending: {summary.get('pending', 0)}"
        )
        print()
        for entry in data.get("tasks", []):
            task = entry.get("task", {})
            result = entry.get("result", {})
            name = task.get("name", "Unnamed")
            status = result.get("status", "unknown")
            icon = get_status_icon(status)
            finished = result.get("finished_at", "")
            extra = f"  ({finished[:16]})" if finished else ""
            print(f"  {icon} {name}{extra}")
    else:
        print(f"{BOLD}Archive files:{RESET}")
        for archive in archives:
            with open(archive) as f:
                data = yaml.safe_load(f)
            summary = data.get("run_summary", {})
            print(
                f"  {archive.name}  "
                f"(done: {summary.get('done', 0)}, "
                f"failed: {summary.get('failed', 0)}, "
                f"total: {summary.get('total', 0)})"
            )


def main():
    # Handle migrate subcommand before argparse
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        run_migrate()
        return

    parser = argparse.ArgumentParser(
        description="t-loop: Automated Claude Code task runner"
    )
    parser.add_argument("--status", "-s", action="store_true", help="Show task status")
    parser.add_argument("--reset", action="store_true", help="Reset all tasks to pending")
    parser.add_argument("--only", type=int, help="Run only specific task number (1-based)")
    parser.add_argument(
        "--confirm", "-i", action="store_true", help="Confirm before each task"
    )
    parser.add_argument(
        "--continue", "-c", dest="continue_on_fail", action="store_true",
        help="Continue even if a task fails",
    )
    parser.add_argument(
        "--archive", nargs="?", const=True, default=None,
        help="List archive files; use 'latest' to show most recent",
    )
    args = parser.parse_args()

    # Handle --archive (exits without running tasks)
    if args.archive is not None:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        show_archives(latest=(args.archive == "latest"))
        return

    ensure_tloop_home()

    config = load_config()
    tasks = config.get("tasks", [])
    defaults = config.get("defaults", {})

    if not tasks:
        print("No tasks defined in tasks.yaml")
        sys.exit(0)

    state = load_state()

    if args.status:
        show_status(tasks, state)
        return

    if args.reset:
        state = {"tasks": {}, "version": 1}
        save_state(state)
        print(f"{GREEN}State reset. All tasks are pending.{RESET}")
        return

    if args.only is not None:
        if args.only < 1 or args.only > len(tasks):
            print(f"{RED}Invalid task number: {args.only}{RESET}")
            sys.exit(1)
        indices = [args.only - 1]
    else:
        indices = list(range(len(tasks)))

    ran_any = False
    for i in indices:
        ts = state.get("tasks", {}).get(str(i), {})
        status = ts.get("status", "pending")

        if status == "done" and args.only is None:
            print(f"⏭️  Task [{i + 1}] already done, skipping")
            continue

        if args.confirm:
            name = tasks[i].get("name", f"Task {i + 1}")
            try:
                resp = input(f"\nRun task [{i + 1}] '{name}'? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                break
            if resp.lower() != "y":
                print("Skipped.")
                continue

        ran_any = True
        success = run_task(tasks[i], i, state, defaults)
        if not success and not args.continue_on_fail:
            print(f"\n{YELLOW}Stopped. Use -c to continue after failures.{RESET}")
            break

    if ran_any:
        print(f"\n{BOLD}--- Final Status ---{RESET}")
        show_status(tasks, state)

    # Archive completed tasks whenever we reach the task loop (not --status/--reset)
    archive_completed_tasks(config, state)

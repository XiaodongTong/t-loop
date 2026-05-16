"""t-loop CLI: Automated Claude Code task runner."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from tloop.git_ops import ensure_clean_git, create_task_branch

SCRIPT_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = SCRIPT_DIR / "tasks.yaml"
STATE_FILE = SCRIPT_DIR / ".tloop-state.json"
LOGS_DIR = SCRIPT_DIR / "logs"

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ensure_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        print(f"{YELLOW}pyyaml not found, installing...{RESET}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyyaml"],
            stdout=subprocess.DEVNULL,
        )
        import yaml
        return yaml


def load_config():
    yaml = ensure_yaml()
    if not TASKS_FILE.exists():
        print(f"{RED}Error: {TASKS_FILE} not found{RESET}")
        print(f"Create tasks.yaml first. See tasks.example.yaml for reference.")
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
        pf = SCRIPT_DIR / prompt_file
        if not pf.exists():
            pf = Path(prompt_file)
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


def main():
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
    args = parser.parse_args()

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

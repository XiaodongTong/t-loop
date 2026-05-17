"""Single task execution for t-loop."""

import os
from datetime import datetime
from pathlib import Path

import config
from git_ops import ensure_clean_git, create_task_branch
from runner.cybervisor import CybervisorRunner
from state import save_state


def expand_dir(d):
    return os.path.expandvars(os.path.expanduser(d))


def resolve_prompt_file(prompt_file, dir_path):
    """Resolve prompt_file: ~ expansion, TLOOP_HOME-relative, then dir-relative."""
    pf = Path(prompt_file).expanduser()
    if pf.is_absolute():
        return pf
    candidate = config.TLOOP_HOME / prompt_file
    if candidate.exists():
        return candidate
    candidate = Path(dir_path) / prompt_file
    if candidate.exists():
        return candidate
    return Path(prompt_file)


def run_task(task, index, state):
    name = task.get("name", f"Task {index + 1}")
    dir_path = expand_dir(task.get("dir", "."))
    prompt = task.get("prompt", "")
    prompt_file = task.get("prompt_file")
    branch_config = task.get("branch", True)

    if not os.path.isdir(dir_path):
        print(f"{config.RED}  Directory not found: {dir_path}{config.RESET}")
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": f"Directory not found: {dir_path}",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False

    resolved_pf = None
    if prompt_file:
        resolved_pf = resolve_prompt_file(prompt_file, dir_path)
        if resolved_pf.exists():
            prompt = resolved_pf.read_text()
        else:
            print(f"{config.RED}  Prompt file not found: {prompt_file}{config.RESET}")
            return False

    if not prompt.strip():
        print(f"{config.RED}  No prompt defined for task: {name}{config.RESET}")
        return False

    print(f"\n{config.BOLD}{'=' * 60}{config.RESET}")
    print(f"{config.BOLD}  Task [{index + 1}]: {name}{config.RESET}")
    print(f"  Directory: {config.CYAN}{dir_path}{config.RESET}")
    print(f"{config.BOLD}{'=' * 60}{config.RESET}\n")

    config.LOGS_DIR.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    log_file = config.LOGS_DIR / f"{index + 1:03d}-{safe_name}.log"

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

    try:
        with open(log_file, "a") as log:
            log.write(f"Started: {started}\n")
            log.write(f"Command: cybervisor run < {'<prompt_file>' if resolved_pf else '<prompt>'}\n")
            log.write("-" * 60 + "\n\n")
            log.flush()

        runner = CybervisorRunner()
        returncode = runner.run(prompt, dir_path, log_file=log_file, prompt_file=resolved_pf)

        if returncode == 0:
            state["tasks"][str(index)] = {
                "status": "done",
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
            }
            save_state(state)
            print(f"\n{config.GREEN}✅ Task [{index + 1}] done{config.RESET}")
        else:
            state["tasks"][str(index)] = {
                "status": "failed",
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
                "returncode": returncode,
            }
            save_state(state)
            print(
                f"\n{config.RED}❌ Task [{index + 1}] failed (exit code: {returncode}){config.RESET}"
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
        print(f"\n{config.RED}❌ Task [{index + 1}] error: {e}{config.RESET}")
        return False

    return True

"""tloop migrate — migrate old data files to ~/.tloop/."""

import shutil
import sys
from pathlib import Path

import yaml

import config


def add_parser(subparsers):
    p = subparsers.add_parser("migrate", help="Migrate old data to ~/.tloop/")
    p.set_defaults(func=handle)


def handle(args):
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
        print(f"{config.YELLOW}No old data files found in {project_root}{config.RESET}")
        print("Nothing to migrate.")
        return

    if config.TASKS_FILE.exists():
        print(f"{config.RED}Conflict: {config.TASKS_FILE} already exists{config.RESET}")
        print("Resolve the conflict manually before migrating.")
        sys.exit(1)

    config.TLOOP_HOME.mkdir(exist_ok=True)
    config.LOGS_DIR.mkdir(exist_ok=True)
    config.ARCHIVE_DIR.mkdir(exist_ok=True)

    if old_tasks.exists():
        shutil.copy2(old_tasks, config.TASKS_FILE)
        print(f"  Migrated: tasks.yaml → {config.TASKS_FILE}")

        data = yaml.safe_load(open(old_tasks)) or {}
        for i, task in enumerate(data.get("tasks", [])):
            pf = task.get("prompt_file")
            if pf and not Path(pf).expanduser().is_absolute():
                print(
                    f"  {config.YELLOW}Warning: task '{task.get('name', f'Task {i + 1}')}' "
                    f"has relative prompt_file '{pf}'{config.RESET}"
                )
                print(f"    Will resolve from {config.TLOOP_HOME} first, then the task's dir.")

    if old_state.exists():
        shutil.copy2(old_state, config.STATE_FILE)
        print(f"  Migrated: .tloop-state.json → {config.STATE_FILE}")

    if old_logs.exists() and old_logs.is_dir():
        for log_file in old_logs.iterdir():
            if log_file.is_file():
                shutil.copy2(log_file, config.LOGS_DIR / log_file.name)
        print(f"  Migrated: logs/ → {config.LOGS_DIR}/")

    print(f"\n{config.GREEN}Migration complete.{config.RESET}")
    print(f"Old files still exist in {project_root} — remove them manually when ready.")

"""State management and archiving for t-loop."""

import json
from datetime import datetime
from pathlib import Path

import yaml

import config


def load_state():
    if config.STATE_FILE.exists():
        with open(config.STATE_FILE) as f:
            return json.load(f)
    return {"tasks": {}, "version": 1}


def save_state(state):
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


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
        print(f"  {icon}  [{i + 1}] {name}{config.RESET}  {config.CYAN}{status}{config.RESET}{extra}")
    print()


def archive_completed_tasks(config_data, state):
    tasks = config_data.get("tasks", [])

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

    config.ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_file = config.ARCHIVE_DIR / f"run-{timestamp}.yaml"
    with open(archive_file, "w") as f:
        yaml.dump(archive_data, f, default_flow_style=False, allow_unicode=True)

    remaining_config = dict(config_data)
    remaining_config["tasks"] = remaining
    with open(config.TASKS_FILE, "w") as f:
        yaml.dump(remaining_config, f, default_flow_style=False, allow_unicode=True)

    save_state({"tasks": {}, "version": 1})

    print(f"\n{config.GREEN}Archived {done_count} completed task(s) to {archive_file.name}{config.RESET}")


def show_archives(latest=False):
    if not config.ARCHIVE_DIR.exists():
        print("No archive files found.")
        return

    archives = sorted(config.ARCHIVE_DIR.glob("run-*.yaml"), reverse=True)
    if not archives:
        print("No archive files found.")
        return

    if latest:
        with open(archives[0]) as f:
            data = yaml.safe_load(f)
        print(f"{config.BOLD}Latest archive: {archives[0].name}{config.RESET}")
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
        print(f"{config.BOLD}Archive files:{config.RESET}")
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

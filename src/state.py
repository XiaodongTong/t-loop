"""State management and archiving for t-loop."""

import json
from datetime import datetime

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
    content = yaml.dump(remaining_config, default_flow_style=False, allow_unicode=True)
    with open(config.TASKS_FILE, "w") as f:
        f.write(config.TASKS_YAML_HEADER + content)

    save_state({"tasks": {}, "version": 1})

    print(f"\n{config.GREEN}Archived {done_count} completed task(s) to {archive_file.name}{config.RESET}")

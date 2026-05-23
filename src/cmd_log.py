"""tloop log — view task logs."""

import sys
from datetime import datetime
from pathlib import Path

import config
from state import load_state


_STATUS_COLORS = {
    "done": config.GREEN,
    "failed": config.RED,
    "running": config.CYAN,
}


def add_parser(subparsers):
    p = subparsers.add_parser("log", help="View task logs")
    p.add_argument("task_number", nargs="?", type=int,
                   help="Show log for task #N (1-based)")
    p.set_defaults(func=handle)


def _color(text, color):
    if sys.stdout.isatty():
        return f"{color}{text}{config.RESET}"
    return text


def _get_log_files():
    if not config.LOGS_DIR.exists():
        return []
    return sorted(config.LOGS_DIR.glob("*.log"))


def _parse_task_number(path):
    name = path.stem
    prefix = name.split("-", 1)[0]
    if prefix.isdigit():
        return int(prefix)
    return None


def _extract_task_name(path):
    try:
        with open(path, errors="replace") as f:
            first_line = f.readline()
        if first_line.startswith("Task:"):
            return first_line.split(":", 1)[1].strip()
    except (OSError, UnicodeDecodeError):
        pass
    name = path.stem
    _, sep, rest = name.partition("-")
    return rest if sep else name


def _format_size(size):
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    else:
        return f"{size / (1024 * 1024):.1f}M"


def _list_logs():
    log_files = _get_log_files()
    if not log_files:
        print("No log files found")
        return

    state = load_state()
    state_tasks = state.get("tasks", {})

    for lf in log_files:
        task_num = _parse_task_number(lf)
        task_name = _extract_task_name(lf)
        stat = lf.stat()
        size_str = _format_size(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

        status = "pending"
        color = config.DIM
        if task_num is not None:
            state_key = str(task_num - 1)
            ts = state_tasks.get(state_key, {})
            status = ts.get("status", "pending")
            color = _STATUS_COLORS.get(status, config.DIM)

        num_display = f"[{task_num}]" if task_num is not None else "[?]"
        line = f"  {num_display} {task_name}  {size_str}  {mtime}"
        print(_color(line, color))


def _show_log(task_number):
    log_files = _get_log_files()
    for lf in log_files:
        num = _parse_task_number(lf)
        if num == task_number:
            try:
                with open(lf, errors="replace") as f:
                    for line in f:
                        sys.stdout.write(line)
            except OSError as e:
                print(f"Error reading {lf.name}: {e}", file=sys.stderr)
                sys.exit(1)
            return

    print(f"No log found for task #{task_number}", file=sys.stderr)
    sys.exit(1)


def handle(args):
    if args.task_number is not None:
        _show_log(args.task_number)
    else:
        _list_logs()

"""Configuration constants and helpers for t-loop."""

import sys
from pathlib import Path

import yaml

TLOOP_HOME = Path.home() / ".tloop"
TASKS_FILE = TLOOP_HOME / "tasks.yaml"
STATE_FILE = TLOOP_HOME / "state.json"
SETTINGS_FILE = TLOOP_HOME / "settings.json"
LOGS_DIR = TLOOP_HOME / "logs"
ARCHIVE_DIR = TLOOP_HOME / "archive"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

TASKS_YAML_HEADER = (
    "# Run 'tloop edit --help' for details on how to write this file.\n"
    "# Project-level AI instructions: ./docs/tloop/constitution.md (auto-loaded by tloop).\n"
)

SAMPLE_TASKS_YAML = TASKS_YAML_HEADER + "tasks: []\n"


def ensure_tloop_home():
    TLOOP_HOME.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    if not TASKS_FILE.exists():
        TASKS_FILE.write_text(SAMPLE_TASKS_YAML)
        print(f"{GREEN}Created {TASKS_FILE}{RESET}")
        print(f"\nEdit ~/.tloop/tasks.yaml to define your tasks, then run tloop run.")
        sys.exit(0)


def load_config():
    if not TASKS_FILE.exists():
        print(f"{RED}Error: {TASKS_FILE} not found{RESET}")
        print(f"Run tloop run to initialize, then edit tasks.yaml.")
        sys.exit(1)
    try:
        with open(TASKS_FILE) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        location = ""
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            location = f" (line {mark.line + 1}, column {mark.column + 1})"
        print(f"{RED}Error: {TASKS_FILE} 解析失败{location}{RESET}")
        if hasattr(e, "problem") and e.problem:
            print(f"  {e.problem}")
        print("请检查 YAML 格式，常见问题：含冒号/特殊字符的值需要用引号包裹。")
        sys.exit(1)

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

SAMPLE_TASKS_YAML = "# Run 'tloop edit --help' for details on how to write this file.\ntasks: []\n"


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
    with open(TASKS_FILE) as f:
        return yaml.safe_load(f) or {}

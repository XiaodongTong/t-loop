"""Configuration constants and helpers for t-loop."""

import sys
from pathlib import Path

import yaml

TLOOP_HOME = Path.home() / ".tloop"
TASKS_FILE = TLOOP_HOME / "tasks.yaml"
STATE_FILE = TLOOP_HOME / "state.json"
LOGS_DIR = TLOOP_HOME / "logs"
ARCHIVE_DIR = TLOOP_HOME / "archive"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

SAMPLE_TASKS_YAML = """\
# t-loop tasks.yaml
# Define your Claude Code automation tasks here.
#
# Location: ~/.tloop/tasks.yaml
#
# Each task runs "cybervisor run <prompt>" in the specified directory.
# Completed tasks are automatically archived after each run cycle.
# View archives with: tloop archive
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

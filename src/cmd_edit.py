"""tloop edit — open ~/.tloop/tasks.yaml in editor, optionally add a task."""

import argparse
import json
import re
import shutil
import subprocess

import yaml

import config

KNOWN_EDITORS = {
    "code": ("Visual Studio Code", "code"),
    "vim": ("Vim", "vim"),
    "nano": ("Nano", "nano"),
}

EDIT_HELP = """\
Open ~/.tloop/tasks.yaml in your editor.

On first run, you will be prompted to choose an editor (VS Code, Vim, Nano,
or a custom command). The choice is saved to ~/.tloop/settings.json.
Override anytime with: tloop edit --editor <command>

Task file format (~/.tloop/tasks.yaml):

  tasks:
    - name: My task
      dir: ~/projects/my-project
      prompt: |
        Describe what Claude should do.
      # OR:
      prompt_file: ./prompts/my-task.md
      branch: true           # true=auto, "custom/name", false=skip
      use: cybervisor        # cybervisor (default) or claude
      max_rounds: 5          # only for use: claude

  Each task runs in the specified directory. Completed tasks are
  archived to ~/.tloop/archive/ after each run cycle.

  Project-level AI instructions can be placed in ./docs/tloop/constitution.md
  within the project directory. If present, tloop will auto-load them as
  constitutional rules when running tasks with the claude runner.
"""


def _load_settings():
    if config.SETTINGS_FILE.exists():
        try:
            return json.loads(config.SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_settings(settings):
    config.TLOOP_HOME.mkdir(exist_ok=True)
    config.SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")


def _prompt_editor():
    options = []
    for key, (label, cmd) in KNOWN_EDITORS.items():
        if shutil.which(cmd):
            options.append((key, label, cmd))

    print(f"{config.BOLD}Choose your editor for tasks.yaml:{config.RESET}\n")
    for i, (key, label, _) in enumerate(options, 1):
        print(f"  {i}) {label}")
    print(f"  {len(options) + 1}) Other (enter command manually)")
    print()

    while True:
        choice = input(f"Enter number [1-{len(options) + 1}]: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1][2]
            if idx == len(options) + 1:
                cmd = input("Enter editor command: ").strip()
                if cmd:
                    return cmd
        print("Invalid choice, try again.")


def _resolve_editor(cli_editor=None):
    if cli_editor:
        return cli_editor
    settings = _load_settings()
    if "editor" in settings:
        return settings["editor"]
    editor = _prompt_editor()
    _save_settings({"editor": editor})
    print(f"{config.GREEN}Editor saved. Change anytime with: tloop edit --editor <command>{config.RESET}\n")
    return editor


def add_parser(subparsers):
    p = subparsers.add_parser(
        "edit",
        help="Open ~/.tloop/tasks.yaml in editor",
        description=EDIT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("path", nargs="?", help="Add a task with this dir and open the file")
    p.add_argument("--editor", help="Override editor command for this session")
    p.set_defaults(func=handle)


def _add_task(path):
    """Append a guided task entry with dir=path to tasks.yaml."""
    config.TLOOP_HOME.mkdir(exist_ok=True)
    if not config.TASKS_FILE.exists():
        config.TASKS_FILE.write_text(config.SAMPLE_TASKS_YAML)

    try:
        data = yaml.safe_load(config.TASKS_FILE.read_text()) or {}
    except yaml.YAMLError:
        data = {}

    tasks = data.get("tasks") or []
    task_num = len(tasks) + 1

    raw = config.TASKS_FILE.read_text()

    # Detect indentation of existing task entries (default: 2 spaces)
    indent = "  "
    m = re.search(r'^(\s*)- \w', raw, re.MULTILINE)
    if m:
        indent = m.group(1)
    inner = indent + "  "

    new_entry = (
        f"{indent}- name: Task {task_num}\n"
        f"{inner}dir: {path}\n"
        f"{inner}prompt: |\n"
        f"{inner}  Describe what Claude should do.\n"
        f"{inner}# prompt or prompt_file\n"
        f"{inner}# prompt_file: ./prompts/my-task.md\n"
        f"{inner}branch: true           # true=auto, \"custom/name\", false=skip\n"
        f"{inner}use: cybervisor        # cybervisor (default) or claude\n"
        f"{inner}max_rounds: 5          # only for use: claude\n"
    )

    stripped = raw.rstrip()

    if stripped.endswith("tasks: []"):
        raw = stripped[: -len("tasks: []")] + "tasks:\n" + new_entry
    else:
        raw = stripped + "\n\n" + new_entry

    config.TASKS_FILE.write_text(raw + "\n")
    print(f"{config.GREEN}Added task 'Task {task_num}' with dir={path}{config.RESET}")


def handle(args):
    path = getattr(args, "path", None)
    if path:
        _add_task(path)

    config.TLOOP_HOME.mkdir(exist_ok=True)
    if not config.TASKS_FILE.exists():
        config.TASKS_FILE.write_text(config.SAMPLE_TASKS_YAML)

    editor = _resolve_editor(getattr(args, "editor", None))
    subprocess.run([editor, str(config.TASKS_FILE)])

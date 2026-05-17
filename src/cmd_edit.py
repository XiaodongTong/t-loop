"""tloop edit — open ~/.tloop/tasks.yaml in editor."""

import argparse
import json
import os
import shutil
import subprocess

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

  Each task runs in the specified directory. Completed tasks are
  archived to ~/.tloop/archive/ after each run cycle.
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
    p.add_argument("--editor", help="Override editor command for this session")
    p.set_defaults(func=handle)


def handle(args):
    config.TLOOP_HOME.mkdir(exist_ok=True)
    if not config.TASKS_FILE.exists():
        config.TASKS_FILE.write_text(config.SAMPLE_TASKS_YAML)

    editor = _resolve_editor(getattr(args, "editor", None))
    subprocess.run([editor, str(config.TASKS_FILE)])

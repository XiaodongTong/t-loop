"""tloop edit — open ~/.tloop/tasks.yaml in editor."""

import argparse
import os
import subprocess

import config


EDIT_HELP = """\
Open ~/.tloop/tasks.yaml in your editor ($EDITOR, defaults to vi).

Task file format (~/.tloop/tasks.yaml):

  defaults:
    model: opus              # optional default model

  tasks:
    - name: My task
      dir: ~/projects/my-project
      prompt: |
        Describe what Claude should do.
      # OR:
      prompt_file: ./prompts/my-task.md
      model: opus            # optional override
      branch: true           # true=auto, "custom/name", false=skip

  Each task runs in the specified directory. Completed tasks are
  archived to ~/.tloop/archive/ after each run cycle.
"""


def add_parser(subparsers):
    p = subparsers.add_parser(
        "edit",
        help="Open ~/.tloop/tasks.yaml in editor",
        description=EDIT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.set_defaults(func=handle)


def handle(args):
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(config.TASKS_FILE)])

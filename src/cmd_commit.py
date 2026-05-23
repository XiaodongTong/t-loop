"""tloop commit — auto-commit dirty working tree via Claude."""

import argparse
from pathlib import Path

import git_ops


def add_parser(subparsers):
    p = subparsers.add_parser(
        "commit",
        help="Auto-commit changes in the working tree",
        description="Commit changes in the current or specified directory using Claude.",
    )
    p.add_argument(
        "-p", "--path",
        default=".",
        help="Path to the git repository (default: current directory)",
    )
    p.add_argument(
        "-m", "--model",
        choices=["haiku", "sonnet", "opus"],
        default="haiku",
        help="Claude model to use for auto-commit (default: haiku)",
    )
    p.set_defaults(func=handle)


def handle(args):
    dir_path = Path(args.path).resolve()

    if not dir_path.is_dir():
        print(f"\033[91mError: {dir_path} is not a directory.\033[0m")
        return

    if not git_ops.is_git_repo(dir_path):
        print(f"\033[91mError: {dir_path} is not a git repository.\033[0m")
        return

    if git_ops.is_git_clean(dir_path):
        print(f"\033[92mWorking tree is already clean.\033[0m")
        return

    success = git_ops.ensure_clean_git(dir_path, "manual commit", model=args.model)
    if success:
        print(f"\033[92mDone.\033[0m")
    else:
        print(f"\033[91mCommit failed.\033[0m")

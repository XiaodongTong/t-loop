"""Git operations for t-loop: auto-commit, branch management, and safety checks."""

import subprocess
from datetime import datetime

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

COMMIT_STAGED_PROMPT = (
    "You are performing a protective auto-commit of STAGED changes in this repository.\n"
    "Follow these steps exactly:\n"
    "1. Run `git diff --cached --name-only` to see what is staged.\n"
    "2. Check each file for sensitive content (e.g., .env, credentials, secret keys, API tokens, private keys). "
    "If you find any sensitive files staged, unstage them with `git restore --staged <file>` and report what you excluded.\n"
    "3. If any files remain staged after the sensitive-file check, commit them with a Chinese conventional-commit message "
    "(format: `<type>: <description>` where type is one of: feat, fix, refactor, docs, style, test, chore, perf, ci, build). "
    "Do NOT use the `--no-verify` flag.\n"
    "4. If nothing remains staged after the sensitive-file check, report that there is nothing to commit.\n"
)

COMMIT_WORKDIR_PROMPT = (
    "You are performing a protective auto-commit of all remaining UNSTAGED changes in this repository.\n"
    "Follow these steps exactly:\n"
    "1. Run `git add -A` to stage all working-directory changes.\n"
    "2. Run `git diff --cached --name-only` to see what is now staged.\n"
    "3. Check each file for sensitive content (e.g., .env, credentials, secret keys, API tokens, private keys). "
    "If you find any sensitive files staged, unstage them with `git restore --staged <file>` and report what you excluded.\n"
    "4. If any files remain staged after the sensitive-file check, commit them with a Chinese conventional-commit message "
    "(format: `<type>: <description>` where type is one of: feat, fix, refactor, docs, style, test, chore, perf, ci, build). "
    "Do NOT use the `--no-verify` flag.\n"
    "5. If nothing remains staged after the sensitive-file check, report that there is nothing to commit.\n"
)


def _git(dir_path, *args):
    result = subprocess.run(
        ["git"] + list(args),
        cwd=dir_path,
        capture_output=True,
        text=True,
    )
    return result


def is_git_repo(dir_path):
    result = _git(dir_path, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def is_git_clean(dir_path):
    result = _git(dir_path, "status", "--porcelain")
    return result.returncode == 0 and result.stdout.strip() == ""


def has_staged_changes(dir_path):
    result = _git(dir_path, "diff", "--cached", "--quiet")
    return result.returncode == 1


def is_detached_head(dir_path):
    result = _git(dir_path, "symbolic-ref", "-q", "HEAD")
    return result.returncode != 0


def branch_exists(dir_path, name):
    result = _git(dir_path, "branch", "--list", name)
    return result.stdout.strip() != ""


def _run_commit_prompt(dir_path, prompt_text, log_file=None):
    result = subprocess.run(
        ["claude", "-p", prompt_text],
        cwd=dir_path,
        capture_output=True,
        text=True,
    )
    if log_file:
        with open(log_file, "a") as log:
            log.write(f"[auto-commit] claude -p exit code: {result.returncode}\n")
            if result.stdout:
                log.write(result.stdout + "\n")
            if result.stderr:
                log.write(result.stderr + "\n")
            log.flush()
    if result.returncode != 0 and log_file is None:
        print(f"{YELLOW}  Auto-commit prompt exited with code {result.returncode}{RESET}")
    return result.returncode == 0


def ensure_clean_git(dir_path, task_name, log_file=None):
    if not is_git_repo(dir_path):
        return True

    if is_git_clean(dir_path):
        return True

    if has_staged_changes(dir_path):
        print(f"{YELLOW}  Dirty working tree detected. Auto-committing staged changes...{RESET}")
        _run_commit_prompt(dir_path, COMMIT_STAGED_PROMPT, log_file)

    if not is_git_clean(dir_path):
        print(f"{YELLOW}  Committing remaining working-directory changes...{RESET}")
        _run_commit_prompt(dir_path, COMMIT_WORKDIR_PROMPT, log_file)

    if is_git_clean(dir_path):
        print(f"{GREEN}  Working tree is now clean.{RESET}")
        return True

    print(f"{RED}  Failed to clean working tree after auto-commit. Skipping task.{RESET}")
    return False


def find_next_available_branch(dir_path, prefix):
    for n in range(1, 1000):
        name = f"{prefix}-{n:03d}"
        if not branch_exists(dir_path, name):
            return name
    return None


def create_task_branch(dir_path, branch_config):
    if not is_git_repo(dir_path):
        return True

    if branch_config is False:
        return True

    if is_detached_head(dir_path):
        print(f"{RED}  Cannot create branch: repository is in detached HEAD state.{RESET}")
        return False

    today = datetime.now().strftime("%Y%m%d")

    if branch_config is True or branch_config is None:
        prefix = f"feature-{today}"
        name = find_next_available_branch(dir_path, prefix)
        if name is None:
            print(f"{RED}  Could not find an available branch name with prefix {prefix}{RESET}")
            return False
    else:
        custom = str(branch_config)
        if not branch_exists(dir_path, custom):
            name = custom
        else:
            prefix = custom
            name = find_next_available_branch(dir_path, prefix)
            if name is None:
                print(f"{RED}  Could not find an available branch name with prefix {prefix}{RESET}")
                return False

    result = _git(dir_path, "checkout", "-b", name)
    if result.returncode != 0:
        print(f"{RED}  Failed to create branch '{name}': {result.stderr.strip()}{RESET}")
        return False

    print(f"{GREEN}  Created and checked out branch: {name}{RESET}")
    return True

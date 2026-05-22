"""Post-task code review via self-critique to improve generated code quality."""

import subprocess
from pathlib import Path

REVIEW_PROMPT = """\
You are performing a critical self-review of code changes just made in this project.

<diff>
{diff}
</diff>

Review the diff for these issues:
1. **Bugs**: Logic errors, off-by-one, null/None handling, race conditions
2. **Security**: Injection vulnerabilities, credential exposure, unsafe operations
3. **Error handling**: Missing error handling for external calls, user input validation
4. **Code quality**: Dead code, duplicated logic, misleading names, unreachable paths
5. **Edge cases**: Empty inputs, boundary conditions, concurrent access

Fix any real issues you find. Do NOT make stylistic changes or add comments.
If no issues are found, output: NO_ISSUES_FOUND

When you have fully completed all fixes (or found no issues), output on its own line:
<promise>COMPLETE</promise>
Do NOT output this unless you have finished everything. If there is still work to do, \
end your response normally — another iteration will pick up where you left off."""


def get_head_commit(dir_path):
    """Return current HEAD commit hash, or None if not a git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=dir_path,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_diff(dir_path, base_commit):
    """Return diff between base_commit and current working tree."""
    result = subprocess.run(
        ["git", "diff", base_commit],
        cwd=dir_path,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def review_changes(dir_path, base_commit, log_file=None):
    """Run post-task code review on all changes since base_commit.

    Non-blocking: returns True/False to indicate review outcome, but
    the calling code should not treat a review failure as a task failure.
    """
    diff = get_diff(dir_path, base_commit)
    if not diff:
        return True

    constitution_path = Path(dir_path) / "docs" / "tloop" / "constitution.md"
    constitution_content = ""
    if constitution_path.exists():
        constitution_content = (
            "<constitution>\n"
            + constitution_path.read_text()
            + "\n</constitution>\n\n"
        )

    prompt = REVIEW_PROMPT.format(diff=diff)
    full_input = constitution_content + prompt

    log = open(log_file, "a") if log_file else open("/dev/null", "a")
    try:
        log.write(f"\n{'=' * 60}\n")
        log.write("[Post-task self-review]\n")
        log.write(f"Base commit: {base_commit[:12]}\n")
        log.write(f"Diff size: {len(diff)} chars\n")
        log.write(f"{'=' * 60}\n\n")
        log.flush()

        process = subprocess.Popen(
            ["claude", "-p", "--dangerously-skip-permissions"],
            cwd=dir_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        process.stdin.write(full_input)
        process.stdin.close()

        output_parts = []
        for line in process.stdout:
            print(line, end="")
            log.write(line)
            output_parts.append(line)

        process.wait()
        log.flush()

        accumulated = "".join(output_parts)
        if process.returncode == 0:
            if "NO_ISSUES_FOUND" in accumulated:
                log.write("\n[Review: no issues found]\n")
            elif "<promise>COMPLETE</promise>" in accumulated:
                log.write("\n[Review: issues found and fixed]\n")
            else:
                log.write("\n[Review: completed]\n")
            return True

        log.write(f"\n[Review: failed with exit code {process.returncode}]\n")
        return False
    finally:
        log.close()

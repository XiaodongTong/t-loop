"""Reusable Claude CLI runner with retry and verification."""

import subprocess

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

DEFAULT_MAX_RETRIES = 3

# Append this to prompts where Claude might just plan instead of executing.
EXECUTION_SUFFIX = (
    "\n\nIMPORTANT: Execute the steps above immediately. "
    "Do NOT ask for confirmation, do NOT just describe what you would do. "
    "Perform every step now using your available tools."
)


def run_claude(prompt, cwd, max_retries=DEFAULT_MAX_RETRIES, verify_fn=None, log_file=None):
    """Run `claude -p` with --dangerously-skip-permissions and optional retry loop.

    Args:
        prompt: The prompt text to send to Claude.
        cwd: Working directory for the subprocess.
        max_retries: Max attempts before giving up.
        verify_fn: Optional callable(cwd) -> bool that checks if the work was actually done.
        log_file: Optional path to append logs.

    Returns:
        True if Claude succeeded (and passed verification if provided), False otherwise.
    """
    enriched_prompt = prompt + EXECUTION_SUFFIX
    cmd = ["claude", "--dangerously-skip-permissions", "--print", enriched_prompt]

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            hint = (
                f"This is attempt {attempt}/{max_retries}. "
                "The previous attempt did not complete the task. "
                "You MUST execute the steps now, not describe them."
            )
            attempt_prompt = prompt + "\n\n" + hint + EXECUTION_SUFFIX
            attempt_cmd = ["claude", "--dangerously-skip-permissions", "--print", attempt_prompt]
        else:
            attempt_cmd = cmd

        print(f"  Running claude (attempt {attempt}/{max_retries})...")
        try:
            result = subprocess.run(
                attempt_cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            print(f"{YELLOW}  Claude timed out after 300s (attempt {attempt}/{max_retries}){RESET}")
            if attempt >= max_retries:
                print(f"{RED}  Max retries reached. Giving up.{RESET}")
                return False
            continue

        if log_file:
            with open(log_file, "a") as log:
                log.write(f"[claude_runner] attempt {attempt}/{max_retries} exit={result.returncode}\n")
                if result.stdout:
                    log.write(result.stdout + "\n")
                if result.stderr:
                    log.write(result.stderr + "\n")
                log.flush()

        if result.returncode != 0:
            print(f"{YELLOW}  Claude exited with code {result.returncode} (attempt {attempt}/{max_retries}){RESET}")
            if attempt < max_retries:
                continue
            return False

        # If no verification function, trust the exit code.
        if verify_fn is None:
            return True

        if verify_fn(cwd):
            return True

        print(f"{YELLOW}  Claude completed but verification failed (attempt {attempt}/{max_retries}){RESET}")
        if attempt >= max_retries:
            print(f"{RED}  Max retries reached. Giving up.{RESET}")
            return False

    return False

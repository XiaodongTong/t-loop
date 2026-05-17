"""Claude Code runner backend with round-loop execution."""

import subprocess
import time

from runner import Runner


class ClaudeRunner(Runner):
    def run(self, prompt, cwd, log_file=None, max_rounds=5):
        """
        Run Claude Code in a loop with configurable round limit.

        Args:
            prompt: The prompt to send to Claude Code
            cwd: Working directory for the task
            log_file: Optional path to log file
            max_rounds: Maximum number of loop iterations (default 5)

        Returns:
            0 on success (completion signal detected), non-zero on failure
        """
        log = open(log_file, "a") if log_file else open("/dev/null", "a")
        try:
            for round_num in range(1, max_rounds + 1):
                log.write(f"\n{'='*60}\n")
                log.write(f"Round {round_num}/{max_rounds}\n")
                log.write(f"{'='*60}\n\n")
                log.flush()

                print(f"\n{'='*60}")
                print(f" Round {round_num}/{max_rounds} ")
                print(f"{'='*60}")

                process = subprocess.Popen(
                    ["claude", "-p", "--dangerously-skip-permissions"],
                    cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                output_parts = []
                process.stdin.write(prompt)
                process.stdin.close()

                for line in process.stdout:
                    print(line, end="")
                    log.write(line)
                    output_parts.append(line)

                process.wait()
                log.flush()

                accumulated = "".join(output_parts)
                if "<promise>COMPLETE</promise>" in accumulated:
                    log.write("\n[Completion signal detected - exiting loop]\n")
                    log.flush()
                    return 0

                if round_num < max_rounds:
                    log.write(f"\n[Round {round_num} complete, sleeping 2s before next round]\n")
                    log.flush()
                    time.sleep(2)

            log.write(f"\n[All {max_rounds} rounds exhausted without completion signal]\n")
            log.flush()
            return 1
        finally:
            log.close()
"""Cybervisor runner backend."""

import subprocess

from runner import Runner


class CybervisorRunner(Runner):
    def run(self, prompt, cwd, log_file=None, prompt_file=None):
        cmd = ["cybervisor", "run"]

        with open(log_file, "a") if log_file else open("/dev/null", "a") as log:
            stdin_fh = open(prompt_file, "r") if prompt_file else None
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdin=stdin_fh if stdin_fh else subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                if not stdin_fh:
                    process.stdin.write(prompt)
                    process.stdin.close()
                for line in process.stdout:
                    print(line, end="")
                    log.write(line)
                log.flush()
                process.wait()
            finally:
                if stdin_fh:
                    stdin_fh.close()

        return process.returncode

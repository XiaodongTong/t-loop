"""Cybervisor runner backend."""

import subprocess

from runner import Runner


class CybervisorRunner(Runner):
    def run(self, prompt, cwd, model=None, log_file=None):
        cmd = ["cybervisor", "run", prompt]
        if model:
            cmd.extend(["--model", model])

        with open(log_file, "a") if log_file else open("/dev/null", "a") as log:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in process.stdout:
                print(line, end="")
                log.write(line)
            log.flush()
            process.wait()

        return process.returncode

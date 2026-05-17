"""Runner base class for t-loop task execution backends."""

from abc import ABC, abstractmethod


class Runner(ABC):
    @abstractmethod
    def run(self, prompt, cwd, log_file=None):
        """Run a task. Returns exit code (0=success)."""
        ...

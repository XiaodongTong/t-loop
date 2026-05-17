"""Tests for ClaudeRunner."""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from runner.claude import ClaudeRunner


class MockProcess:
    def __init__(self, stdout_lines, returncode=0):
        self._stdout_lines = stdout_lines
        self.returncode = returncode
        self.stdin = MagicMock()

    @property
    def stdout(self):
        return iter(self._stdout_lines)

    def wait(self):
        pass


class ClaudeRunnerTests(unittest.TestCase):

    def test_completion_signal_exits_early(self):
        runner = ClaudeRunner()
        mock_process = MockProcess(["Some output\n", "<promise>COMPLETE</promise>\n", "More output\n"])
        with patch("subprocess.Popen", return_value=mock_process):
            with patch("time.sleep"):
                returncode = runner.run("test prompt", "/tmp", max_rounds=5)
        self.assertEqual(returncode, 0)

    def test_no_signal_exhausts_rounds(self):
        runner = ClaudeRunner()
        mock_process = MockProcess(["Some output\n", "No completion here\n"])
        with patch("subprocess.Popen", return_value=mock_process):
            with patch("time.sleep"):
                returncode = runner.run("test prompt", "/tmp", max_rounds=3)
        self.assertEqual(returncode, 1)

    def test_default_max_rounds_is_5(self):
        runner = ClaudeRunner()
        calls = []
        mock_process = MockProcess(["No signal\n"])

        def track_popen(*args, **kwargs):
            calls.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=track_popen):
            with patch("time.sleep"):
                runner.run("test prompt", "/tmp")
        self.assertEqual(len(calls), 5)

    def test_custom_max_rounds_respected(self):
        runner = ClaudeRunner()
        calls = []
        mock_process = MockProcess(["No signal\n"])

        def track_popen(*args, **kwargs):
            calls.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=track_popen):
            with patch("time.sleep"):
                runner.run("test prompt", "/tmp", max_rounds=3)
        self.assertEqual(len(calls), 3)

    def test_first_round_complete_exits_early(self):
        runner = ClaudeRunner()
        mock_process = MockProcess(["<promise>COMPLETE</promise>\n"])
        with patch("subprocess.Popen", return_value=mock_process):
            with patch("time.sleep") as mock_sleep:
                returncode = runner.run("test prompt", "/tmp", max_rounds=5)
        self.assertEqual(returncode, 0)
        mock_sleep.assert_not_called()

    def test_sleep_between_rounds(self):
        runner = ClaudeRunner()
        mock_process = MockProcess(["No signal\n"])
        with patch("subprocess.Popen", return_value=mock_process):
            with patch("time.sleep") as mock_sleep:
                runner.run("test prompt", "/tmp", max_rounds=3)
        self.assertEqual(mock_sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
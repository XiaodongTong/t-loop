#!/usr/bin/env python3
"""Tests for t-loop main module."""

import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import importlib
git_ops = importlib.import_module("git_ops")
tl = importlib.import_module("t-loop")


def _init_git_repo(tmpdir):
    subprocess.run(["git", "init", tmpdir], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", tmpdir, "config", "user.email", "test@test.com"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", tmpdir, "config", "user.name", "Test"],
        capture_output=True, check=True,
    )
    readme = os.path.join(tmpdir, "README.md")
    with open(readme, "w") as f:
        f.write("hello")
    subprocess.run(["git", "-C", tmpdir, "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", tmpdir, "commit", "-m", "init"],
        capture_output=True, check=True,
    )


class RunTaskGitIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)

    @patch.object(tl, "ensure_clean_git", return_value=True)
    @patch.object(tl, "create_task_branch", return_value=True)
    @patch("subprocess.Popen")
    def test_run_task_with_git_phases_pass(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["output\n"])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "branch": "feat/test",
        }
        result = tl.run_task(task, 0, state, {})
        self.assertTrue(result)
        mock_clean.assert_called_once()
        mock_branch.assert_called_once_with(self.tmpdir, "feat/test")

    @patch.object(tl, "ensure_clean_git", return_value=False)
    def test_run_task_git_clean_failure_skips_task(self, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
        }
        result = tl.run_task(task, 0, state, {})
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertIn("auto-commit", state["tasks"]["0"]["error"])

    @patch.object(tl, "ensure_clean_git", return_value=True)
    @patch.object(tl, "create_task_branch", return_value=False)
    def test_run_task_branch_failure_skips_task(self, mock_branch, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "branch": True,
        }
        result = tl.run_task(task, 0, state, {})
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertIn("branch", state["tasks"]["0"]["error"])

    @patch.object(tl, "ensure_clean_git", return_value=False)
    def test_state_never_running_on_git_failure(self, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
        }
        tl.run_task(task, 0, state, {})
        self.assertNotEqual(state["tasks"]["0"]["status"], "running")
        self.assertEqual(state["tasks"]["0"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()

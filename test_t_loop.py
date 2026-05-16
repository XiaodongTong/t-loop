#!/usr/bin/env python3
"""Tests for t-loop Git safety protection features."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# t-loop.py has a hyphen in its name, so use importlib
import importlib
tl = importlib.import_module("t-loop")


class GitHelperTests(unittest.TestCase):
    """Tests for low-level Git helper functions using real temp Git repos."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.name", "Test"],
            capture_output=True, check=True,
        )
        readme = os.path.join(self.tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("hello")
        subprocess.run(["git", "-C", self.tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "init"],
            capture_output=True, check=True,
        )

    def test_is_git_repo_true(self):
        self.assertTrue(tl.is_git_repo(self.tmpdir))

    def test_is_git_repo_false(self):
        non_git = tempfile.mkdtemp()
        self.assertFalse(tl.is_git_repo(non_git))

    def test_is_git_clean_true(self):
        self.assertTrue(tl.is_git_clean(self.tmpdir))

    def test_is_git_clean_dirty_untracked(self):
        Path(self.tmpdir, "new.txt").write_text("dirty")
        self.assertFalse(tl.is_git_clean(self.tmpdir))

    def test_is_git_clean_dirty_modified(self):
        Path(self.tmpdir, "README.md").write_text("changed")
        self.assertFalse(tl.is_git_clean(self.tmpdir))

    def test_has_staged_changes_true(self):
        Path(self.tmpdir, "staged.txt").write_text("staged")
        subprocess.run(["git", "-C", self.tmpdir, "add", "staged.txt"], capture_output=True)
        self.assertTrue(tl.has_staged_changes(self.tmpdir))

    def test_has_staged_changes_false(self):
        self.assertFalse(tl.has_staged_changes(self.tmpdir))

    def test_is_detached_head_false(self):
        self.assertFalse(tl.is_detached_head(self.tmpdir))

    def test_is_detached_head_true(self):
        result = subprocess.run(
            ["git", "-C", self.tmpdir, "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        sha = result.stdout.strip()
        subprocess.run(["git", "-C", self.tmpdir, "checkout", sha], capture_output=True)
        self.assertTrue(tl.is_detached_head(self.tmpdir))

    def test_branch_exists_true(self):
        subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "test-branch"],
            capture_output=True,
        )
        self.assertTrue(tl.branch_exists(self.tmpdir, "test-branch"))

    def test_branch_exists_false(self):
        self.assertFalse(tl.branch_exists(self.tmpdir, "nonexistent"))


class EnsureCleanGitTests(unittest.TestCase):
    """Tests for ensure_clean_git with mocked cybervisor calls."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.name", "Test"],
            capture_output=True, check=True,
        )
        readme = os.path.join(self.tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("hello")
        subprocess.run(["git", "-C", self.tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "init"],
            capture_output=True, check=True,
        )

    @patch.object(tl, "_run_commit_prompt")
    def test_clean_repo_skips_commit(self, mock_commit):
        result = tl.ensure_clean_git(self.tmpdir, "test-task")
        self.assertTrue(result)
        mock_commit.assert_not_called()

    def test_non_git_repo_returns_true(self):
        non_git = tempfile.mkdtemp()
        result = tl.ensure_clean_git(non_git, "test-task")
        self.assertTrue(result)

    @patch.object(tl, "_run_commit_prompt")
    @patch.object(tl, "is_git_clean")
    @patch.object(tl, "has_staged_changes", return_value=True)
    def test_dirty_repo_triggers_staged_then_workdir(self, mock_staged, mock_clean, mock_commit):
        # Flow: is_git_clean returns False initially, then after staged commit still False,
        # then after workdir commit returns True
        mock_clean.side_effect = [False, False, True]
        result = tl.ensure_clean_git(self.tmpdir, "test-task")
        self.assertTrue(result)
        self.assertEqual(mock_commit.call_count, 2)

    @patch.object(tl, "_run_commit_prompt")
    @patch.object(tl, "is_git_clean")
    def test_uncleanable_repo_returns_false(self, mock_clean, mock_commit):
        Path(self.tmpdir, "dirty.txt").write_text("dirty")
        mock_clean.return_value = False
        result = tl.ensure_clean_git(self.tmpdir, "test-task")
        self.assertFalse(result)


class BranchManagementTests(unittest.TestCase):
    """Tests for branch management functions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.name", "Test"],
            capture_output=True, check=True,
        )
        readme = os.path.join(self.tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("hello")
        subprocess.run(["git", "-C", self.tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "init"],
            capture_output=True, check=True,
        )

    def test_non_git_repo_returns_true(self):
        non_git = tempfile.mkdtemp()
        self.assertTrue(tl.create_task_branch(non_git, True))

    def test_branch_false_skips_creation(self):
        self.assertTrue(tl.create_task_branch(self.tmpdir, False))
        result = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        )
        self.assertNotIn("feature-", result.stdout.strip())

    def test_branch_true_auto_generates_name(self):
        today = datetime.now().strftime("%Y%m%d")
        result = tl.create_task_branch(self.tmpdir, True)
        self.assertTrue(result)
        branch = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertTrue(branch.startswith(f"feature-{today}-"))

    def test_branch_none_auto_generates_name(self):
        today = datetime.now().strftime("%Y%m%d")
        result = tl.create_task_branch(self.tmpdir, None)
        self.assertTrue(result)
        branch = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertTrue(branch.startswith(f"feature-{today}-"))

    def test_custom_branch_name(self):
        result = tl.create_task_branch(self.tmpdir, "feat/login")
        self.assertTrue(result)
        branch = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(branch, "feat/login")

    def test_custom_branch_collision_gets_suffix(self):
        subprocess.run(
            ["git", "-C", self.tmpdir, "checkout", "-b", "feat/login"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "checkout", "-"],
            capture_output=True,
        )

        result = tl.create_task_branch(self.tmpdir, "feat/login")
        self.assertTrue(result)
        branch = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(branch, "feat/login-001")

    def test_detached_head_returns_false(self):
        result = subprocess.run(
            ["git", "-C", self.tmpdir, "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        sha = result.stdout.strip()
        subprocess.run(
            ["git", "-C", self.tmpdir, "checkout", sha],
            capture_output=True,
        )
        result = tl.create_task_branch(self.tmpdir, True)
        self.assertFalse(result)


class FindNextAvailableBranchTests(unittest.TestCase):
    """Tests for find_next_available_branch."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.name", "Test"],
            capture_output=True, check=True,
        )
        readme = os.path.join(self.tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("hello")
        subprocess.run(["git", "-C", self.tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "init"],
            capture_output=True, check=True,
        )

    def test_first_available(self):
        name = tl.find_next_available_branch(self.tmpdir, "feature-20260517")
        self.assertEqual(name, "feature-20260517-001")

    def test_collision_increments(self):
        subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "feature-20260517-001"],
            capture_output=True,
        )
        name = tl.find_next_available_branch(self.tmpdir, "feature-20260517")
        self.assertEqual(name, "feature-20260517-002")

    def test_returns_valid_name(self):
        name = tl.find_next_available_branch(self.tmpdir, "test-prefix")
        self.assertIsNotNone(name)
        self.assertTrue(name.startswith("test-prefix-"))


class RunTaskGitIntegrationTests(unittest.TestCase):
    """Tests for run_task() Git phase integration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.name", "Test"],
            capture_output=True, check=True,
        )
        readme = os.path.join(self.tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("hello")
        subprocess.run(["git", "-C", self.tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "init"],
            capture_output=True, check=True,
        )

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

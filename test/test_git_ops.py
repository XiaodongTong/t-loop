#!/usr/bin/env python3
"""Tests for tloop.git_ops module."""

import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from tloop.git_ops import (
    branch_exists,
    create_task_branch,
    ensure_clean_git,
    find_next_available_branch,
    has_staged_changes,
    is_detached_head,
    is_git_clean,
    is_git_repo,
)


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


class GitHelperTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)

    def test_is_git_repo_true(self):
        self.assertTrue(is_git_repo(self.tmpdir))

    def test_is_git_repo_false(self):
        non_git = tempfile.mkdtemp()
        self.assertFalse(is_git_repo(non_git))

    def test_is_git_clean_true(self):
        self.assertTrue(is_git_clean(self.tmpdir))

    def test_is_git_clean_dirty_untracked(self):
        Path(self.tmpdir, "new.txt").write_text("dirty")
        self.assertFalse(is_git_clean(self.tmpdir))

    def test_is_git_clean_dirty_modified(self):
        Path(self.tmpdir, "README.md").write_text("changed")
        self.assertFalse(is_git_clean(self.tmpdir))

    def test_has_staged_changes_true(self):
        Path(self.tmpdir, "staged.txt").write_text("staged")
        subprocess.run(["git", "-C", self.tmpdir, "add", "staged.txt"], capture_output=True)
        self.assertTrue(has_staged_changes(self.tmpdir))

    def test_has_staged_changes_false(self):
        self.assertFalse(has_staged_changes(self.tmpdir))

    def test_is_detached_head_false(self):
        self.assertFalse(is_detached_head(self.tmpdir))

    def test_is_detached_head_true(self):
        result = subprocess.run(
            ["git", "-C", self.tmpdir, "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        sha = result.stdout.strip()
        subprocess.run(["git", "-C", self.tmpdir, "checkout", sha], capture_output=True)
        self.assertTrue(is_detached_head(self.tmpdir))

    def test_branch_exists_true(self):
        subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "test-branch"],
            capture_output=True,
        )
        self.assertTrue(branch_exists(self.tmpdir, "test-branch"))

    def test_branch_exists_false(self):
        self.assertFalse(branch_exists(self.tmpdir, "nonexistent"))


class EnsureCleanGitTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)

    @patch("tloop.git_ops._run_commit_prompt")
    def test_clean_repo_skips_commit(self, mock_commit):
        result = ensure_clean_git(self.tmpdir, "test-task")
        self.assertTrue(result)
        mock_commit.assert_not_called()

    def test_non_git_repo_returns_true(self):
        non_git = tempfile.mkdtemp()
        result = ensure_clean_git(non_git, "test-task")
        self.assertTrue(result)

    @patch("tloop.git_ops._run_commit_prompt")
    @patch("tloop.git_ops.is_git_clean")
    @patch("tloop.git_ops.has_staged_changes", return_value=True)
    def test_dirty_repo_triggers_staged_then_workdir(self, mock_staged, mock_clean, mock_commit):
        mock_clean.side_effect = [False, False, True]
        result = ensure_clean_git(self.tmpdir, "test-task")
        self.assertTrue(result)
        self.assertEqual(mock_commit.call_count, 2)

    @patch("tloop.git_ops._run_commit_prompt")
    @patch("tloop.git_ops.is_git_clean")
    def test_uncleanable_repo_returns_false(self, mock_clean, mock_commit):
        Path(self.tmpdir, "dirty.txt").write_text("dirty")
        mock_clean.return_value = False
        result = ensure_clean_git(self.tmpdir, "test-task")
        self.assertFalse(result)


class BranchManagementTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)

    def test_non_git_repo_returns_true(self):
        non_git = tempfile.mkdtemp()
        self.assertTrue(create_task_branch(non_git, True))

    def test_branch_false_skips_creation(self):
        self.assertTrue(create_task_branch(self.tmpdir, False))
        result = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        )
        self.assertNotIn("feature-", result.stdout.strip())

    def test_branch_true_auto_generates_name(self):
        today = datetime.now().strftime("%Y%m%d")
        result = create_task_branch(self.tmpdir, True)
        self.assertTrue(result)
        branch = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertTrue(branch.startswith(f"feature-{today}-"))

    def test_branch_none_auto_generates_name(self):
        today = datetime.now().strftime("%Y%m%d")
        result = create_task_branch(self.tmpdir, None)
        self.assertTrue(result)
        branch = subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "--show-current"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertTrue(branch.startswith(f"feature-{today}-"))

    def test_custom_branch_name(self):
        result = create_task_branch(self.tmpdir, "feat/login")
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

        result = create_task_branch(self.tmpdir, "feat/login")
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
        result = create_task_branch(self.tmpdir, True)
        self.assertFalse(result)


class FindNextAvailableBranchTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)

    def test_first_available(self):
        name = find_next_available_branch(self.tmpdir, "feature-20260517")
        self.assertEqual(name, "feature-20260517-001")

    def test_collision_increments(self):
        subprocess.run(
            ["git", "-C", self.tmpdir, "branch", "feature-20260517-001"],
            capture_output=True,
        )
        name = find_next_available_branch(self.tmpdir, "feature-20260517")
        self.assertEqual(name, "feature-20260517-002")

    def test_returns_valid_name(self):
        name = find_next_available_branch(self.tmpdir, "test-prefix")
        self.assertIsNotNone(name)
        self.assertTrue(name.startswith("test-prefix-"))


if __name__ == "__main__":
    unittest.main()

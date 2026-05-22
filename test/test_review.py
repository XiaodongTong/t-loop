"""Tests for post-task code review (review.py)."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import review as review_mod


class GetHeadCommitTests(unittest.TestCase):
    def test_returns_commit_hash(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123def456\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = review_mod.get_head_commit("/some/dir")
        self.assertEqual(result, "abc123def456")
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "HEAD"],
            cwd="/some/dir",
            capture_output=True,
            text=True,
        )

    def test_returns_none_on_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = review_mod.get_head_commit("/not/a/repo")
        self.assertIsNone(result)


class GetDiffTests(unittest.TestCase):
    def test_returns_diff(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/file.py b/file.py\n+new line\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = review_mod.get_diff("/some/dir", "abc123")
        self.assertIn("+new line", result)
        mock_run.assert_called_once_with(
            ["git", "diff", "abc123"],
            cwd="/some/dir",
            capture_output=True,
            text=True,
        )

    def test_returns_empty_on_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = review_mod.get_diff("/some/dir", "abc123")
        self.assertEqual(result, "")

    def test_returns_empty_string_for_no_changes(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = review_mod.get_diff("/some/dir", "abc123")
        self.assertEqual(result, "")


class ReviewChangesTests(unittest.TestCase):
    def _mock_process(self, stdout_lines, returncode=0):
        proc = MagicMock()
        proc.stdout = iter(stdout_lines)
        proc.returncode = returncode
        proc.stdin = MagicMock()
        return proc

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_no_diff_skips_review(self, mock_run, mock_popen):
        mock_diff_result = MagicMock()
        mock_diff_result.returncode = 0
        mock_diff_result.stdout = ""
        mock_run.return_value = mock_diff_result

        result = review_mod.review_changes("/some/dir", "abc123", log_file="/tmp/test.log")
        self.assertTrue(result)
        mock_popen.assert_not_called()

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_review_with_no_issues(self, mock_run, mock_popen):
        mock_diff_result = MagicMock()
        mock_diff_result.returncode = 0
        mock_diff_result.stdout = "diff content here"
        mock_run.return_value = mock_diff_result

        mock_proc = self._mock_process(["NO_ISSUES_FOUND\n", "<promise>COMPLETE</promise>\n"])
        mock_popen.return_value = mock_proc

        with patch("builtins.open", mock_open()):
            result = review_mod.review_changes("/some/dir", "abc123", log_file="/tmp/test.log")
        self.assertTrue(result)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_review_with_fixes(self, mock_run, mock_popen):
        mock_diff_result = MagicMock()
        mock_diff_result.returncode = 0
        mock_diff_result.stdout = "diff content here"
        mock_run.return_value = mock_diff_result

        mock_proc = self._mock_process(["Fixed a bug\n", "<promise>COMPLETE</promise>\n"])
        mock_popen.return_value = mock_proc

        with patch("builtins.open", mock_open()):
            result = review_mod.review_changes("/some/dir", "abc123", log_file="/tmp/test.log")
        self.assertTrue(result)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_review_failure_returns_false(self, mock_run, mock_popen):
        mock_diff_result = MagicMock()
        mock_diff_result.returncode = 0
        mock_diff_result.stdout = "diff content here"
        mock_run.return_value = mock_diff_result

        mock_proc = self._mock_process(["error\n"], returncode=1)
        mock_popen.return_value = mock_proc

        with patch("builtins.open", mock_open()):
            result = review_mod.review_changes("/some/dir", "abc123", log_file="/tmp/test.log")
        self.assertFalse(result)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_constitution_loaded_when_present(self, mock_run, mock_popen):
        mock_diff_result = MagicMock()
        mock_diff_result.returncode = 0
        mock_diff_result.stdout = "diff content"
        mock_run.return_value = mock_diff_result

        mock_proc = self._mock_process(["<promise>COMPLETE</promise>\n"])
        mock_popen.return_value = mock_proc

        constitution_content = "# coding standards\nuse type hints"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=constitution_content):
                with patch("builtins.open", mock_open()):
                    result = review_mod.review_changes("/some/dir", "abc123", log_file="/tmp/test.log")

        written = mock_proc.stdin.write.call_args[0][0]
        self.assertIn("<constitution>", written)
        self.assertIn("coding standards", written)
        self.assertTrue(result)


class ReviewPromptTests(unittest.TestCase):
    def test_prompt_contains_review_categories(self):
        self.assertIn("Bugs", review_mod.REVIEW_PROMPT)
        self.assertIn("Security", review_mod.REVIEW_PROMPT)
        self.assertIn("Error handling", review_mod.REVIEW_PROMPT)
        self.assertIn("Code quality", review_mod.REVIEW_PROMPT)
        self.assertIn("Edge cases", review_mod.REVIEW_PROMPT)

    def test_prompt_contains_completion_signal(self):
        self.assertIn("<promise>COMPLETE</promise>", review_mod.REVIEW_PROMPT)


if __name__ == "__main__":
    unittest.main()

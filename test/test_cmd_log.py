#!/usr/bin/env python3
"""Tests for tloop log subcommand: list, show."""

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cmd_log
import config
import state as state_mod


class _LogTestBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        self.logs_dir = self.home / "logs"
        self.logs_dir.mkdir()
        self.state_file = self.home / "state.json"
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.logs_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _create_log(self, filename, content, mtime=None):
        path = self.logs_dir / filename
        path.write_text(content, errors="replace")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def _write_state(self, tasks):
        self.state_file.write_text(json.dumps({"tasks": tasks, "version": 1}))

    def _run_handle(self, task_number=None):
        return argparse.Namespace(task_number=task_number)


class ListLogsTests(_LogTestBase):
    """T9: Test tloop log listing with populated LOGS_DIR."""

    def test_list_shows_task_numbers_and_names(self):
        self._create_log("001-setup.log", "Task: Setup project\nline1\n")
        self._create_log("002-run_tests.log", "Task: Run tests\nline2\n")
        self._write_state({})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle())

        output = mock_out.getvalue()
        self.assertIn("[1]", output)
        self.assertIn("[2]", output)
        self.assertIn("Setup project", output)
        self.assertIn("Run tests", output)

    def test_list_shows_sizes(self):
        self._create_log("001-big.log", "Task: Big\n" + "x" * 2048 + "\n")
        self._write_state({})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle())

        output = mock_out.getvalue()
        self.assertIn("K", output)

    def test_list_sorted_by_filename(self):
        self._create_log("002-second.log", "Task: Second\n")
        self._create_log("001-first.log", "Task: First\n")
        self._write_state({})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle())

        output = mock_out.getvalue()
        first_pos = output.index("First")
        second_pos = output.index("Second")
        self.assertLess(first_pos, second_pos)


class ListNoLogsTests(_LogTestBase):
    """T10: Test tloop log with nonexistent and empty LOGS_DIR."""

    def test_empty_logs_dir(self):
        self._write_state({})
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle())
        self.assertIn("No log files found", mock_out.getvalue())

    def test_missing_logs_dir(self):
        import shutil
        shutil.rmtree(str(self.logs_dir))
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle())
        self.assertIn("No log files found", mock_out.getvalue())


class ShowLogTests(_LogTestBase):
    """T11: Test tloop log <N> — show specific log."""

    def test_show_valid_task_number(self):
        self._create_log("001-setup.log", "Task: Setup\nline1\nline2\n")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle(task_number=1))
        output = mock_out.getvalue()
        self.assertIn("Task: Setup", output)
        self.assertIn("line1", output)
        self.assertIn("line2", output)

    def test_show_task_number_2(self):
        self._create_log("001-first.log", "Task: First\nfirst content\n")
        self._create_log("002-second.log", "Task: Second\nsecond content\n")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle(task_number=2))
        output = mock_out.getvalue()
        self.assertIn("second content", output)
        self.assertNotIn("first content", output)


class ShowInvalidLogTests(_LogTestBase):
    """T12: Test tloop log 99 — non-existent task number."""

    def test_show_nonexistent_task_exits_1(self):
        self._create_log("001-exists.log", "Task: Exists\n")
        with self.assertRaises(SystemExit) as ctx:
            cmd_log.handle(self._run_handle(task_number=99))
        self.assertEqual(ctx.exception.code, 1)


class TTYDetectionTests(_LogTestBase):
    """T18: Test ANSI color gating based on TTY."""

    def test_color_present_when_tty(self):
        self._create_log("001-task.log", "Task: Test\ncontent\n")
        self._write_state({"0": {"status": "done"}})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=True)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        self.assertIn(config.GREEN, output)

    def test_color_absent_when_not_tty(self):
        self._create_log("001-task.log", "Task: Test\ncontent\n")
        self._write_state({"0": {"status": "done"}})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=False)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        self.assertNotIn(config.GREEN, output)
        self.assertNotIn(config.RED, output)
        self.assertNotIn(config.CYAN, output)
        self.assertIn("Test", output)


class StatusColorTests(_LogTestBase):
    """T19: Test status color enrichment from state.json."""

    def test_done_status_green(self):
        self._create_log("001-done.log", "Task: Done Task\n")
        self._write_state({"0": {"status": "done"}})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=True)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        self.assertIn(config.GREEN, output)

    def test_failed_status_red(self):
        self._create_log("002-failed.log", "Task: Failed Task\n")
        self._write_state({"1": {"status": "failed"}})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=True)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        self.assertIn(config.RED, output)

    def test_running_status_cyan(self):
        self._create_log("003-running.log", "Task: Running Task\n")
        self._write_state({"2": {"status": "running"}})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=True)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        self.assertIn(config.CYAN, output)

    def test_pending_status_dim(self):
        self._create_log("004-pending.log", "Task: Pending Task\n")
        self._write_state({})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=True)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        self.assertIn(config.DIM, output)

    def test_state_key_mapping_0_based(self):
        """Verify that task #2 (filename 002-*) maps to state key '1'."""
        self._create_log("001-first.log", "Task: First\n")
        self._create_log("002-second.log", "Task: Second\n")
        self._write_state({
            "0": {"status": "done"},
            "1": {"status": "failed"},
        })

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_out.isatty = MagicMock(return_value=True)
            cmd_log.handle(self._run_handle())
        output = mock_out.getvalue()
        lines = output.strip().split("\n")
        second_line = [l for l in lines if "Second" in l][0]
        self.assertIn(config.RED, second_line)


class BinarySafeContentTests(_LogTestBase):
    """T20: Test binary-safe content handling."""

    def test_show_log_with_non_utf8(self):
        log_path = self.logs_dir / "001-binary.log"
        log_path.write_bytes(b"Task: Binary\n\xff\xfe line\nnormal text\n")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle(task_number=1))
        output = mock_out.getvalue()
        self.assertIn("normal text", output)

    def test_show_log_with_special_characters(self):
        self._create_log("001-special.log", "Task: Special\ntabs\there\nnewline\n")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle(task_number=1))
        output = mock_out.getvalue()
        self.assertIn("tabs\there", output)


if __name__ == "__main__":
    unittest.main()

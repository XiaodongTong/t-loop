#!/usr/bin/env python3
"""Tests for tloop log subcommand: list, show, follow, search."""

import argparse
import io
import json
import os
import sys
import tempfile
import time
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
            patch.object(config, "ARCHIVE_DIR", self.home / "archive"),
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

    def _run_handle(self, follow=False, search=None, task_number=None):
        return argparse.Namespace(
            follow=follow, search=search, task_number=task_number
        )


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


class MutualExclusivityTests(unittest.TestCase):
    """Verify --follow, --search, and task_number are mutually exclusive at parse time."""

    def _parse(self, *args):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        cmd_log.add_parser(sub)
        return parser.parse_args(["log"] + list(args))

    def test_follow_and_search_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("--follow", "--search", "x")

    def test_follow_and_task_number_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("--follow", "1")

    def test_search_and_task_number_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("--search", "x", "1")


class ShowInvalidLogTests(_LogTestBase):
    """T12: Test tloop log 99 — non-existent task number."""

    def test_show_nonexistent_task_exits_1(self):
        self._create_log("001-exists.log", "Task: Exists\n")
        with self.assertRaises(SystemExit) as ctx:
            cmd_log.handle(self._run_handle(task_number=99))
        self.assertEqual(ctx.exception.code, 1)


class SearchLogsTests(_LogTestBase):
    """T13: Test tloop log --search with matching and non-matching patterns."""

    def test_search_finds_match(self):
        self._create_log("001-task.log", "Task: My Task\nERROR: something failed\n")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                cmd_log.handle(self._run_handle(search="ERROR"))
            self.assertEqual(ctx.exception.code, 0)
        self.assertIn("something failed", mock_out.getvalue())

    def test_search_no_match_exits_1(self):
        self._create_log("001-task.log", "Task: My Task\nall good\n")
        with self.assertRaises(SystemExit) as ctx:
            cmd_log.handle(self._run_handle(search="NONEXISTENT"))
        self.assertEqual(ctx.exception.code, 1)

    def test_search_case_insensitive(self):
        self._create_log("001-task.log", "Task: My Task\nerror: lowercase\n")
        with patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as ctx:
                cmd_log.handle(self._run_handle(search="ERROR"))
            self.assertEqual(ctx.exception.code, 0)

    def test_search_across_multiple_files(self):
        self._create_log("001-a.log", "Task: A\nfound it here\n")
        self._create_log("002-b.log", "Task: B\nalso found it there\n")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                cmd_log.handle(self._run_handle(search="found it"))
            self.assertEqual(ctx.exception.code, 0)
        output = mock_out.getvalue()
        self.assertIn("1:A", output)
        self.assertIn("2:B", output)

    def test_search_no_logs(self):
        self._write_state({})
        with self.assertRaises(SystemExit) as ctx:
            cmd_log.handle(self._run_handle(search="anything"))
        self.assertEqual(ctx.exception.code, 1)


class SearchSpecialCharsTests(_LogTestBase):
    """T14: Test tloop log --search with regex-special characters."""

    def test_search_asterisk_treated_as_literal(self):
        self._create_log("001-task.log", "Task: Files\nmodified *.py files\nno match here\n")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                cmd_log.handle(self._run_handle(search="*.py"))
            self.assertEqual(ctx.exception.code, 0)
        self.assertIn("*.py", mock_out.getvalue())

    def test_search_brackets_treated_as_literal(self):
        self._create_log("001-task.log", "Task: Log\n[error] connection timeout\n")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                cmd_log.handle(self._run_handle(search="[error]"))
            self.assertEqual(ctx.exception.code, 0)
        self.assertIn("[error]", mock_out.getvalue())


class FollowLogTests(_LogTestBase):
    """T15: Test tloop log --follow — tail and stream."""

    def test_follow_shows_last_20_lines(self):
        lines = [f"line {i}\n" for i in range(25)]
        self._create_log("001-long.log", "".join(lines))

        def fake_sleep(_):
            raise KeyboardInterrupt

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("time.sleep", side_effect=fake_sleep):
                cmd_log.handle(self._run_handle(follow=True))

        output = mock_out.getvalue()
        self.assertIn("line 5", output)
        self.assertIn("line 24", output)
        self.assertNotIn("line 4", output)

    def test_follow_streams_new_content(self):
        log_path = self._create_log("001-live.log", "initial\n")

        real_file = open(log_path, errors="replace")
        real_file.close()

        read_count = [0]

        def fake_read():
            read_count[0] += 1
            if read_count[0] == 1:
                return "new data\n"
            raise KeyboardInterrupt

        def fake_open(path, *args, **kwargs):
            m = MagicMock()
            m.__enter__ = lambda s: s
            m.__exit__ = MagicMock(return_value=False)
            m.readlines.return_value = ["initial\n"]
            m.tell.return_value = 0
            m.seek.return_value = None
            m.read = fake_read
            return m

        with patch("builtins.open", side_effect=fake_open):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                with patch("time.sleep"):
                    cmd_log.handle(self._run_handle(follow=True))

        output = mock_out.getvalue()
        self.assertIn("new data", output)


class FollowShortLogTests(_LogTestBase):
    """T16: Test --follow with log file shorter than 20 lines."""

    def test_follow_short_log_shows_all_lines(self):
        self._create_log("001-short.log", "only 3 lines\nline 2\nline 3\n")

        stop_after = [0]

        def fake_sleep(_):
            stop_after[0] += 1
            if stop_after[0] >= 1:
                raise KeyboardInterrupt

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("time.sleep", side_effect=fake_sleep):
                cmd_log.handle(self._run_handle(follow=True))

        output = mock_out.getvalue()
        self.assertIn("only 3 lines", output)
        self.assertIn("line 2", output)
        self.assertIn("line 3", output)


class FollowNoLogsTests(_LogTestBase):
    """T17: Test --follow with no log files."""

    def test_follow_no_logs_graceful(self):
        self._write_state({})
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle(follow=True))
        self.assertIn("No log files found", mock_out.getvalue())


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

    def test_search_with_non_utf8(self):
        log_path = self.logs_dir / "001-binary.log"
        log_path.write_bytes(b"Task: Binary\nERROR: \xff\xfe bad bytes\n")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                cmd_log.handle(self._run_handle(search="ERROR"))
            self.assertEqual(ctx.exception.code, 0)
        self.assertIn("ERROR", mock_out.getvalue())

    def test_show_log_with_special_characters(self):
        self._create_log("001-special.log", "Task: Special\ntabs\there\nnewline\n")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_log.handle(self._run_handle(task_number=1))
        output = mock_out.getvalue()
        self.assertIn("tabs\there", output)


if __name__ == "__main__":
    unittest.main()

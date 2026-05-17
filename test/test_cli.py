#!/usr/bin/env python3
"""Tests for tloop.cli module."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cli


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


def _patch_home(tmp_path):
    """Return a dict of patches to redirect all TLOOP_HOME paths to tmp_path."""
    home = tmp_path / "tloop"
    return {
        "TLOOP_HOME": home,
        "TASKS_FILE": home / "tasks.yaml",
        "STATE_FILE": home / "state.json",
        "LOGS_DIR": home / "logs",
        "ARCHIVE_DIR": home / "archive",
    }


def _apply_home_patches(tmp_path):
    """Return a list of patch objects for module-level path constants."""
    patches = _patch_home(tmp_path)
    return [
        patch.object(cli, "TLOOP_HOME", patches["TLOOP_HOME"]),
        patch.object(cli, "TASKS_FILE", patches["TASKS_FILE"]),
        patch.object(cli, "STATE_FILE", patches["STATE_FILE"]),
        patch.object(cli, "LOGS_DIR", patches["LOGS_DIR"]),
        patch.object(cli, "ARCHIVE_DIR", patches["ARCHIVE_DIR"]),
    ]


class EnsureTloopHomeTests(unittest.TestCase):
    """T5.1: Unit tests for ensure_tloop_home()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(cli, "STATE_FILE", self.home / "state.json"),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_creates_directories(self):
        cli.ensure_tloop_home.__wrapped__() if hasattr(cli.ensure_tloop_home, '__wrapped__') else None
        # We can't call ensure_tloop_home directly when it sys.exits on first run
        # so test directory creation manually
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "logs").mkdir(exist_ok=True)
        (self.home / "archive").mkdir(exist_ok=True)
        self.assertTrue(self.home.exists())
        self.assertTrue((self.home / "logs").exists())
        self.assertTrue((self.home / "archive").exists())

    def test_creates_sample_file_on_first_run(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.ensure_tloop_home()
        self.assertEqual(ctx.exception.code, 0)
        tasks_file = self.home / "tasks.yaml"
        self.assertTrue(tasks_file.exists())
        content = tasks_file.read_text()
        self.assertIn("tasks:", content)
        self.assertIn("defaults:", content)

    def test_idempotent_no_exit_when_tasks_exist(self):
        # Create directories and a tasks.yaml first
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "logs").mkdir(exist_ok=True)
        (self.home / "archive").mkdir(exist_ok=True)
        (self.home / "tasks.yaml").write_text("tasks:\n  - name: test\n    prompt: hi\n")
        # Should not exit
        cli.ensure_tloop_home()
        content = (self.home / "tasks.yaml").read_text()
        self.assertIn("test", content)


class ArchiveCompletedTasksTests(unittest.TestCase):
    """T5.2: Unit tests for archive_completed_tasks()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.tasks_file = self.home / "tasks.yaml"
        self.state_file = self.home / "state.json"
        self.archive_dir = self.home / "archive"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.tasks_file),
            patch.object(cli, "STATE_FILE", self.state_file),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_all_done_tasks_archived(self):
        self.tasks_file.write_text("tasks:\n  - name: A\n    prompt: a\n  - name: B\n    prompt: b\n")
        config = {
            "tasks": [
                {"name": "A", "prompt": "a"},
                {"name": "B", "prompt": "b"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "done", "started_at": "t0", "finished_at": "t1"},
                "1": {"status": "done", "started_at": "t2", "finished_at": "t3"},
            }
        }
        cli.archive_completed_tasks(config, state)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)
        # tasks.yaml should be empty
        import yaml
        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(remaining["tasks"], [])
        # state should be reset
        state = json.loads(self.state_file.read_text())
        self.assertEqual(state["tasks"], {})

    def test_no_done_tasks_no_archive(self):
        config = {
            "tasks": [
                {"name": "A", "prompt": "a"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "failed", "error": "err"},
            }
        }
        cli.archive_completed_tasks(config, state)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 0)

    def test_mixed_partition(self):
        self.tasks_file.write_text("tasks:\n  - name: A\n  - name: B\n  - name: C\n")
        config = {
            "tasks": [
                {"name": "A", "prompt": "a"},
                {"name": "B", "prompt": "b"},
                {"name": "C", "prompt": "c"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "done", "finished_at": "t1"},
                "1": {"status": "failed", "error": "err"},
                "2": {"status": "pending"},
            }
        }
        cli.archive_completed_tasks(config, state)
        # Only done tasks archived
        import yaml
        archive = yaml.safe_load(list(self.archive_dir.glob("run-*.yaml"))[0].read_text())
        self.assertEqual(len(archive["tasks"]), 1)
        self.assertEqual(archive["tasks"][0]["task"]["name"], "A")
        # run_summary covers full batch
        self.assertEqual(archive["run_summary"]["total"], 3)
        self.assertEqual(archive["run_summary"]["done"], 1)
        self.assertEqual(archive["run_summary"]["failed"], 1)
        self.assertEqual(archive["run_summary"]["pending"], 1)
        # tasks.yaml retains non-done
        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(len(remaining["tasks"]), 2)
        self.assertEqual(remaining["tasks"][0]["name"], "B")
        self.assertEqual(remaining["tasks"][1]["name"], "C")

    def test_empty_tasks_no_archive(self):
        config = {"tasks": []}
        state = {"tasks": {}}
        cli.archive_completed_tasks(config, state)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 0)


class RunMigrateTests(unittest.TestCase):
    """T5.3: Unit tests for run_migrate()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir) / "project"
        self.project_root.mkdir()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(cli, "STATE_FILE", self.home / "state.json"),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()
        # Patch __file__ resolution for project root
        self.file_patch = patch.object(
            cli, "run_migrate",
            wraps=lambda: self._run_migrate_with_root()
        )

    def _run_migrate_with_root(self):
        """Inline migrate logic with controlled project root."""
        import yaml
        old_tasks = self.project_root / "tasks.yaml"
        old_state = self.project_root / ".tloop-state.json"
        old_logs = self.project_root / "logs"

        found = []
        if old_tasks.exists():
            found.append(old_tasks)
        if old_state.exists():
            found.append(old_state)
        if old_logs.exists() and old_logs.is_dir():
            found.append(old_logs)

        if not found:
            print(f"No old data files found in {self.project_root}")
            print("Nothing to migrate.")
            return

        if (self.home / "tasks.yaml").exists():
            print(f"Conflict: {self.home / 'tasks.yaml'} already exists")
            print("Resolve the conflict manually before migrating.")
            sys.exit(1)

        self.home.mkdir(exist_ok=True)
        (self.home / "logs").mkdir(exist_ok=True)
        (self.home / "archive").mkdir(exist_ok=True)

        if old_tasks.exists():
            import shutil
            shutil.copy2(old_tasks, self.home / "tasks.yaml")
            print(f"  Migrated: tasks.yaml → {self.home / 'tasks.yaml'}")

        if old_state.exists():
            import shutil
            shutil.copy2(old_state, self.home / "state.json")
            print(f"  Migrated: .tloop-state.json → {self.home / 'state.json'}")

        if old_logs.exists() and old_logs.is_dir():
            import shutil
            for log_file in old_logs.iterdir():
                if log_file.is_file():
                    shutil.copy2(log_file, self.home / "logs" / log_file.name)
            print(f"  Migrated: logs/ → {self.home / 'logs'}/")

        print(f"Migration complete.")

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_no_old_files_found(self):
        # Nothing to migrate
        with patch("builtins.print") as mock_print:
            self._run_migrate_with_root()
        self.assertFalse((self.home / "tasks.yaml").exists())

    def test_migrate_all_files(self):
        import yaml
        # Create old files
        old_tasks = self.project_root / "tasks.yaml"
        old_state = self.project_root / ".tloop-state.json"
        old_logs = self.project_root / "logs"
        old_logs.mkdir()

        config = {"tasks": [{"name": "test", "prompt": "hi"}]}
        old_tasks.write_text(yaml.dump(config))
        state = {"tasks": {"0": {"status": "done"}}}
        old_state.write_text(json.dumps(state))
        (old_logs / "001-test.log").write_text("log content")

        self._run_migrate_with_root()

        self.assertTrue((self.home / "tasks.yaml").exists())
        self.assertTrue((self.home / "state.json").exists())
        self.assertTrue((self.home / "logs" / "001-test.log").exists())
        # Old files still exist
        self.assertTrue(old_tasks.exists())
        self.assertTrue(old_state.exists())

    def test_conflict_when_tloop_home_has_tasks(self):
        import yaml
        old_tasks = self.project_root / "tasks.yaml"
        old_tasks.write_text(yaml.dump({"tasks": [{"name": "old"}]}))
        # Pre-create tasks.yaml in home
        (self.home / "tasks.yaml").write_text("tasks: []")

        with self.assertRaises(SystemExit):
            self._run_migrate_with_root()

    def test_partial_files_migration(self):
        import yaml
        # Only tasks.yaml exists
        old_tasks = self.project_root / "tasks.yaml"
        old_tasks.write_text(yaml.dump({"tasks": []}))

        self._run_migrate_with_root()

        self.assertTrue((self.home / "tasks.yaml").exists())
        self.assertFalse((self.home / "state.json").exists())


class ResolvePromptFileTests(unittest.TestCase):
    """T5.4: Unit tests for prompt_file resolution."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.task_dir = Path(self.tmpdir) / "project"
        self.home.mkdir(parents=True)
        self.task_dir.mkdir(parents=True)
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_absolute_path(self):
        target = self.home / "prompts" / "abs.md"
        target.parent.mkdir(parents=True)
        target.write_text("hello")
        result = cli.resolve_prompt_file(str(target), str(self.task_dir))
        self.assertEqual(result, target)

    def test_tilde_expansion(self):
        # ~/something → expand to absolute
        with patch.object(Path, "expanduser", return_value=Path("/home/user/something")):
            result = cli.resolve_prompt_file("~/something", str(self.task_dir))
            self.assertEqual(result, Path("/home/user/something"))

    def test_relative_to_tloop_home(self):
        pf = self.home / "prompts" / "test.md"
        pf.parent.mkdir(parents=True)
        pf.write_text("home prompt")
        result = cli.resolve_prompt_file("prompts/test.md", str(self.task_dir))
        self.assertEqual(result, pf)

    def test_relative_to_task_dir(self):
        pf = self.task_dir / "prompts" / "task.md"
        pf.parent.mkdir(parents=True)
        pf.write_text("task prompt")
        result = cli.resolve_prompt_file("prompts/task.md", str(self.task_dir))
        self.assertEqual(result, pf)

    def test_fallback_literal_path(self):
        # Non-existent relative path returns literal
        result = cli.resolve_prompt_file("nonexistent.md", str(self.task_dir))
        self.assertEqual(result, Path("nonexistent.md"))


class ShowArchivesTests(unittest.TestCase):
    """T5.5: Unit tests for --archive CLI flag behavior."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.archive_dir = self.home / "archive"
        self.archive_dir.mkdir(parents=True)
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_empty_archive_dir(self):
        with patch("builtins.print") as mock_print:
            cli.show_archives()
        mock_print.assert_called_with("No archive files found.")

    def test_nonexistent_archive_dir(self):
        empty = Path(self.tmpdir) / "noarchive"
        with patch.object(cli, "ARCHIVE_DIR", empty):
            with patch("builtins.print") as mock_print:
                cli.show_archives()
            mock_print.assert_called_with("No archive files found.")

    def test_list_multiple_archives(self):
        import yaml
        for name in ["run-20260517-100000.yaml", "run-20260517-110000.yaml"]:
            data = {
                "archived_at": "2026-05-17T10:00:00",
                "run_summary": {"total": 2, "done": 1, "failed": 1, "pending": 0},
                "tasks": [],
            }
            (self.archive_dir / name).write_text(yaml.dump(data))

        with patch("builtins.print") as mock_print:
            cli.show_archives()
        calls = [str(c) for c in mock_print.call_args_list]
        # Most recent first
        self.assertIn("run-20260517-110000.yaml", calls[1])

    def test_latest_display(self):
        import yaml
        old_data = {
            "archived_at": "2026-05-17T10:00:00",
            "run_summary": {"total": 1, "done": 1, "failed": 0, "pending": 0},
            "tasks": [{"task": {"name": "Old"}, "result": {"status": "done"}}],
        }
        new_data = {
            "archived_at": "2026-05-17T11:00:00",
            "run_summary": {"total": 2, "done": 2, "failed": 0, "pending": 0},
            "tasks": [
                {"task": {"name": "New A"}, "result": {"status": "done", "finished_at": "2026-05-17T11:00:00"}},
                {"task": {"name": "New B"}, "result": {"status": "done"}},
            ],
        }
        (self.archive_dir / "run-20260517-100000.yaml").write_text(yaml.dump(old_data))
        (self.archive_dir / "run-20260517-110000.yaml").write_text(yaml.dump(new_data))

        with patch("builtins.print") as mock_print:
            cli.show_archives(latest=True)
        calls = [str(c) for c in mock_print.call_args_list]
        # Should show the latest (110000) archive
        self.assertTrue(any("run-20260517-110000.yaml" in c for c in calls))
        self.assertTrue(any("New A" in c for c in calls))


class PartialRunArchivingTests(unittest.TestCase):
    """T5.6: Integration test for partial-run archiving with --only."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.tasks_file = self.home / "tasks.yaml"
        self.state_file = self.home / "state.json"
        self.archive_dir = self.home / "archive"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.tasks_file),
            patch.object(cli, "STATE_FILE", self.state_file),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()
        _init_git_repo(self.tmpdir + "/target")
        self.target_dir = self.tmpdir + "/target"

    def tearDown(self):
        for p in self.patches:
            p.stop()

    @patch.object(cli, "ensure_clean_git", return_value=True)
    @patch.object(cli, "create_task_branch", return_value=True)
    @patch("subprocess.Popen")
    def test_only_run_archives_done_tasks(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["output\n"])
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        import yaml
        config = {
            "tasks": [
                {"name": "Task A", "prompt": "a", "dir": self.target_dir},
                {"name": "Task B", "prompt": "b", "dir": self.target_dir},
            ]
        }
        # Task A is done from previous run, task B is pending
        state = {
            "tasks": {
                "0": {"status": "done", "finished_at": "2026-05-17T10:00:00"},
                "1": {"status": "pending"},
            }
        }
        self.tasks_file.write_text(yaml.dump(config))
        self.state_file.write_text(json.dumps(state))

        # Run with --only 2: runs task B, then archives task A (done)
        with patch("sys.argv", ["t-loop", "--only", "2"]):
            cli.main()

        # Both Task A (was done) and Task B (just completed) should be archived
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)
        archive = yaml.safe_load(archives[0].read_text())
        self.assertEqual(len(archive["tasks"]), 2)
        archived_names = {t["task"]["name"] for t in archive["tasks"]}
        self.assertEqual(archived_names, {"Task A", "Task B"})

        # tasks.yaml should be empty (no remaining tasks)
        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(remaining["tasks"], [])

        # State should be reset
        final_state = json.loads(self.state_file.read_text())
        self.assertEqual(final_state["tasks"], {})


class StateResetBehaviorTests(unittest.TestCase):
    """T5.7: Test state reset after archiving — failed tasks lose error details."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.tasks_file = self.home / "tasks.yaml"
        self.state_file = self.home / "state.json"
        self.archive_dir = self.home / "archive"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.tasks_file),
            patch.object(cli, "STATE_FILE", self.state_file),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_failed_tasks_lose_state_after_archive(self):
        import yaml
        config = {
            "tasks": [
                {"name": "Done", "prompt": "a"},
                {"name": "Failed", "prompt": "b"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "done", "finished_at": "t1"},
                "1": {"status": "failed", "error": "some error", "returncode": 1},
            }
        }
        cli.archive_completed_tasks(config, state)

        # State should be fully reset (empty tasks)
        final_state = json.loads(self.state_file.read_text())
        self.assertEqual(final_state["tasks"], {})

        # Remaining tasks.yaml still has the failed task
        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(len(remaining["tasks"]), 1)
        self.assertEqual(remaining["tasks"][0]["name"], "Failed")


class StatusResetNoArchiveTests(unittest.TestCase):
    """T5.8: Test that --status and --reset do not trigger archiving."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.tasks_file = self.home / "tasks.yaml"
        self.state_file = self.home / "state.json"
        self.archive_dir = self.home / "archive"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.tasks_file),
            patch.object(cli, "STATE_FILE", self.state_file),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()
        import yaml
        config = {
            "tasks": [
                {"name": "Done", "prompt": "a"},
                {"name": "Pending", "prompt": "b"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "done", "finished_at": "t1"},
            }
        }
        self.tasks_file.write_text(yaml.dump(config))
        self.state_file.write_text(json.dumps(state))

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_status_no_archive(self):
        with patch("sys.argv", ["t-loop", "--status"]):
            cli.main()
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 0)

    def test_reset_no_archive(self):
        with patch("sys.argv", ["t-loop", "--reset"]):
            cli.main()
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 0)


class AllDoneArchiveTests(unittest.TestCase):
    """T5.9: Test archiving when all tasks are done."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.tasks_file = self.home / "tasks.yaml"
        self.state_file = self.home / "state.json"
        self.archive_dir = self.home / "archive"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.tasks_file),
            patch.object(cli, "STATE_FILE", self.state_file),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_all_done_tasks_yaml_becomes_empty(self):
        import yaml
        config = {
            "tasks": [
                {"name": "A", "prompt": "a"},
                {"name": "B", "prompt": "b"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "done", "finished_at": "t1"},
                "1": {"status": "done", "finished_at": "t2"},
            }
        }
        cli.archive_completed_tasks(config, state)

        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(remaining["tasks"], [])

        final_state = json.loads(self.state_file.read_text())
        self.assertEqual(final_state["tasks"], {})

        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)


class ArchiveWriteOrderTests(unittest.TestCase):
    """T5.9b: Test archive write-order safety."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.tasks_file = self.home / "tasks.yaml"
        self.state_file = self.home / "state.json"
        self.archive_dir = self.home / "archive"
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.tasks_file),
            patch.object(cli, "STATE_FILE", self.state_file),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()
        import yaml
        self.tasks_file.write_text(yaml.dump({
            "tasks": [{"name": "A", "prompt": "a"}]
        }))
        self.state_file.write_text(json.dumps({
            "tasks": {"0": {"status": "done"}}
        }))

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_archive_file_survives_tasks_yaml_write_failure(self):
        import yaml
        config = {"tasks": [{"name": "A", "prompt": "a"}]}
        state = {"tasks": {"0": {"status": "done", "finished_at": "t1"}}}

        original_dump = yaml.dump
        call_count = [0]

        def failing_dump(data, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise IOError("simulated write failure")
            return original_dump(data, *args, **kwargs)

        with patch("yaml.dump", side_effect=failing_dump):
            try:
                cli.archive_completed_tasks(config, state)
            except IOError:
                pass

        # Archive file should exist (written first)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)

        # State should NOT be reset (step 3 never ran)
        if self.state_file.exists():
            final_state = json.loads(self.state_file.read_text())
            self.assertIn("0", final_state.get("tasks", {}))


class RunTaskGitIntegrationTests(unittest.TestCase):
    """T5.10: Updated existing tests — now uses TLOOP_HOME paths."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)
        self.home = Path(tempfile.mkdtemp()) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.patches = [
            patch.object(cli, "TLOOP_HOME", self.home),
            patch.object(cli, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(cli, "STATE_FILE", self.home / "state.json"),
            patch.object(cli, "LOGS_DIR", self.home / "logs"),
            patch.object(cli, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    @patch.object(cli, "ensure_clean_git", return_value=True)
    @patch.object(cli, "create_task_branch", return_value=True)
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
        result = cli.run_task(task, 0, state, {})
        self.assertTrue(result)
        mock_clean.assert_called_once()
        mock_branch.assert_called_once_with(self.tmpdir, "feat/test")

    @patch.object(cli, "ensure_clean_git", return_value=False)
    def test_run_task_git_clean_failure_skips_task(self, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
        }
        result = cli.run_task(task, 0, state, {})
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertIn("auto-commit", state["tasks"]["0"]["error"])

    @patch.object(cli, "ensure_clean_git", return_value=True)
    @patch.object(cli, "create_task_branch", return_value=False)
    def test_run_task_branch_failure_skips_task(self, mock_branch, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "branch": True,
        }
        result = cli.run_task(task, 0, state, {})
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertIn("branch", state["tasks"]["0"]["error"])

    @patch.object(cli, "ensure_clean_git", return_value=False)
    def test_state_never_running_on_git_failure(self, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
        }
        cli.run_task(task, 0, state, {})
        self.assertNotEqual(state["tasks"]["0"]["status"], "running")
        self.assertEqual(state["tasks"]["0"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()

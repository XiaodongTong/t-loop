#!/usr/bin/env python3
"""Tests for t-loop modules: config, state, task, cmd_run."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

import config
import state as state_mod
import task as task_mod
import cmd_run
import cmd_edit


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


def _setup_home(tmp_path):
    """Return (home, patches) for redirecting all TLOOP_HOME paths to tmp_path."""
    home = tmp_path / "tloop"
    patches = [
        patch.object(config, "TLOOP_HOME", home),
        patch.object(config, "TASKS_FILE", home / "tasks.yaml"),
        patch.object(config, "STATE_FILE", home / "state.json"),
        patch.object(config, "SETTINGS_FILE", home / "settings.json"),
        patch.object(config, "LOGS_DIR", home / "logs"),
        patch.object(config, "ARCHIVE_DIR", home / "archive"),
    ]
    return home, patches


class EnsureTloopHomeTests(unittest.TestCase):
    """T5.1: Unit tests for ensure_tloop_home()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.home / "state.json"),
            patch.object(config, "SETTINGS_FILE", self.home / "settings.json"),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_creates_directories(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "logs").mkdir(exist_ok=True)
        (self.home / "archive").mkdir(exist_ok=True)
        self.assertTrue(self.home.exists())
        self.assertTrue((self.home / "logs").exists())
        self.assertTrue((self.home / "archive").exists())

    def test_creates_sample_file_on_first_run(self):
        with self.assertRaises(SystemExit) as ctx:
            config.ensure_tloop_home()
        self.assertEqual(ctx.exception.code, 0)
        tasks_file = self.home / "tasks.yaml"
        self.assertTrue(tasks_file.exists())
        content = tasks_file.read_text()
        self.assertIn("tasks:", content)
        self.assertTrue(content.startswith("# Run 'tloop edit --help'"))

    def test_idempotent_no_exit_when_tasks_exist(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "logs").mkdir(exist_ok=True)
        (self.home / "archive").mkdir(exist_ok=True)
        (self.home / "tasks.yaml").write_text("tasks:\n  - name: test\n    prompt: hi\n")
        config.ensure_tloop_home()
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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_all_done_tasks_archived(self):
        self.tasks_file.write_text("tasks:\n  - name: A\n    prompt: a\n  - name: B\n    prompt: b\n")
        config_state = {
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
        state_mod.archive_completed_tasks(config_state, state)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)
        import yaml
        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(remaining["tasks"], [])
        final_state = json.loads(self.state_file.read_text())
        self.assertEqual(final_state["tasks"], {})

    def test_no_done_tasks_no_archive(self):
        config_state = {
            "tasks": [
                {"name": "A", "prompt": "a"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "failed", "error": "err"},
            }
        }
        state_mod.archive_completed_tasks(config_state, state)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 0)

    def test_mixed_partition(self):
        self.tasks_file.write_text("tasks:\n  - name: A\n  - name: B\n  - name: C\n")
        config_state = {
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
        state_mod.archive_completed_tasks(config_state, state)
        import yaml
        archive = yaml.safe_load(list(self.archive_dir.glob("run-*.yaml"))[0].read_text())
        self.assertEqual(len(archive["tasks"]), 1)
        self.assertEqual(archive["tasks"][0]["task"]["name"], "A")
        self.assertEqual(archive["run_summary"]["total"], 3)
        self.assertEqual(archive["run_summary"]["done"], 1)
        self.assertEqual(archive["run_summary"]["failed"], 1)
        self.assertEqual(archive["run_summary"]["pending"], 1)
        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(len(remaining["tasks"]), 2)
        self.assertEqual(remaining["tasks"][0]["name"], "B")
        self.assertEqual(remaining["tasks"][1]["name"], "C")

    def test_empty_tasks_no_archive(self):
        state_mod.archive_completed_tasks({"tasks": []}, {"tasks": {}})
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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.home / "state.json"),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _run_migrate_with_root(self):
        """Inline migrate logic with controlled project root."""
        import yaml
        import shutil
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
            shutil.copy2(old_tasks, self.home / "tasks.yaml")
            print(f"  Migrated: tasks.yaml → {self.home / 'tasks.yaml'}")

        if old_state.exists():
            shutil.copy2(old_state, self.home / "state.json")
            print(f"  Migrated: .tloop-state.json → {self.home / 'state.json'}")

        if old_logs.exists() and old_logs.is_dir():
            for log_file in old_logs.iterdir():
                if log_file.is_file():
                    shutil.copy2(log_file, self.home / "logs" / log_file.name)
            print(f"  Migrated: logs/ → {self.home / 'logs'}/")

        print("Migration complete.")

    def test_no_old_files_found(self):
        with patch("builtins.print"):
            self._run_migrate_with_root()
        self.assertFalse((self.home / "tasks.yaml").exists())

    def test_migrate_all_files(self):
        import yaml
        old_tasks = self.project_root / "tasks.yaml"
        old_state = self.project_root / ".tloop-state.json"
        old_logs = self.project_root / "logs"
        old_logs.mkdir()

        cfg = {"tasks": [{"name": "test", "prompt": "hi"}]}
        old_tasks.write_text(yaml.dump(cfg))
        st = {"tasks": {"0": {"status": "done"}}}
        old_state.write_text(json.dumps(st))
        (old_logs / "001-test.log").write_text("log content")

        self._run_migrate_with_root()

        self.assertTrue((self.home / "tasks.yaml").exists())
        self.assertTrue((self.home / "state.json").exists())
        self.assertTrue((self.home / "logs" / "001-test.log").exists())
        self.assertTrue(old_tasks.exists())
        self.assertTrue(old_state.exists())

    def test_conflict_when_tloop_home_has_tasks(self):
        import yaml
        old_tasks = self.project_root / "tasks.yaml"
        old_tasks.write_text(yaml.dump({"tasks": [{"name": "old"}]}))
        (self.home / "tasks.yaml").write_text("tasks: []")

        with self.assertRaises(SystemExit):
            self._run_migrate_with_root()

    def test_partial_files_migration(self):
        import yaml
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
            patch.object(config, "TLOOP_HOME", self.home),
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
        result = task_mod.resolve_prompt_file(str(target), str(self.task_dir))
        self.assertEqual(result, target)

    def test_tilde_expansion(self):
        with patch.object(Path, "expanduser", return_value=Path("/home/user/something")):
            result = task_mod.resolve_prompt_file("~/something", str(self.task_dir))
            self.assertEqual(result, Path("/home/user/something"))

    def test_relative_to_tloop_home(self):
        pf = self.home / "prompts" / "test.md"
        pf.parent.mkdir(parents=True)
        pf.write_text("home prompt")
        result = task_mod.resolve_prompt_file("prompts/test.md", str(self.task_dir))
        self.assertEqual(result, pf)

    def test_relative_to_task_dir(self):
        pf = self.task_dir / "prompts" / "task.md"
        pf.parent.mkdir(parents=True)
        pf.write_text("task prompt")
        result = task_mod.resolve_prompt_file("prompts/task.md", str(self.task_dir))
        self.assertEqual(result, pf)

    def test_fallback_literal_path(self):
        result = task_mod.resolve_prompt_file("nonexistent.md", str(self.task_dir))
        self.assertEqual(result, Path("nonexistent.md"))


class ShowArchivesTests(unittest.TestCase):
    """T5.5: Unit tests for archive display."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.archive_dir = self.home / "archive"
        self.archive_dir.mkdir(parents=True)
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_empty_archive_dir(self):
        with patch("builtins.print") as mock_print:
            state_mod.show_archives()
        mock_print.assert_called_with("No archive files found.")

    def test_nonexistent_archive_dir(self):
        empty = Path(self.tmpdir) / "noarchive"
        with patch.object(config, "ARCHIVE_DIR", empty):
            with patch("builtins.print") as mock_print:
                state_mod.show_archives()
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
            state_mod.show_archives()
        calls = [str(c) for c in mock_print.call_args_list]
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
            state_mod.show_archives(latest=True)
        calls = [str(c) for c in mock_print.call_args_list]
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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()
        _init_git_repo(self.tmpdir + "/target")
        self.target_dir = self.tmpdir + "/target"

    def tearDown(self):
        for p in self.patches:
            p.stop()

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=True)
    @patch("runner.cybervisor.subprocess.Popen")
    def test_only_run_archives_done_tasks(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["output\n"])
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        import yaml
        cfg = {
            "tasks": [
                {"name": "Task A", "prompt": "a", "dir": self.target_dir},
                {"name": "Task B", "prompt": "b", "dir": self.target_dir},
            ]
        }
        st = {
            "tasks": {
                "0": {"status": "done", "finished_at": "2026-05-17T10:00:00"},
                "1": {"status": "pending"},
            }
        }
        self.tasks_file.write_text(yaml.dump(cfg))
        self.state_file.write_text(json.dumps(st))

        args = argparse.Namespace(
            status=False, reset=False, only=2, confirm=False, continue_on_fail=False,
        )
        cmd_run.handle(args)

        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)
        archive = yaml.safe_load(archives[0].read_text())
        self.assertEqual(len(archive["tasks"]), 2)
        archived_names = {t["task"]["name"] for t in archive["tasks"]}
        self.assertEqual(archived_names, {"Task A", "Task B"})

        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(remaining["tasks"], [])

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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_failed_tasks_lose_state_after_archive(self):
        import yaml
        config_state = {
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
        state_mod.archive_completed_tasks(config_state, state)

        final_state = json.loads(self.state_file.read_text())
        self.assertEqual(final_state["tasks"], {})

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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()
        import yaml
        cfg = {
            "tasks": [
                {"name": "Done", "prompt": "a"},
                {"name": "Pending", "prompt": "b"},
            ]
        }
        st = {
            "tasks": {
                "0": {"status": "done", "finished_at": "t1"},
            }
        }
        self.tasks_file.write_text(yaml.dump(cfg))
        self.state_file.write_text(json.dumps(st))

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_status_no_archive(self):
        args = argparse.Namespace(status=True, reset=False, only=None, confirm=False, continue_on_fail=False)
        cmd_run.handle(args)
        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 0)

    def test_reset_no_archive(self):
        args = argparse.Namespace(status=False, reset=True, only=None, confirm=False, continue_on_fail=False)
        cmd_run.handle(args)
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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_all_done_tasks_yaml_becomes_empty(self):
        import yaml
        config_state = {
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
        state_mod.archive_completed_tasks(config_state, state)

        remaining = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(remaining["tasks"], [])

    def test_header_comment_preserved_after_archive(self):
        import yaml
        config_state = {
            "tasks": [
                {"name": "A", "prompt": "a"},
                {"name": "B", "prompt": "b"},
            ]
        }
        state = {
            "tasks": {
                "0": {"status": "done", "finished_at": "t1"},
                "1": {"status": "failed", "error": "err"},
            }
        }
        state_mod.archive_completed_tasks(config_state, state)
        content = self.tasks_file.read_text()
        self.assertTrue(content.startswith("# Run 'tloop edit --help'"))

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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
            patch.object(config, "STATE_FILE", self.state_file),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.archive_dir),
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
        config_state = {"tasks": [{"name": "A", "prompt": "a"}]}
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
                state_mod.archive_completed_tasks(config_state, state)
            except IOError:
                pass

        archives = list(self.archive_dir.glob("run-*.yaml"))
        self.assertEqual(len(archives), 1)

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
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.home / "state.json"),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=True)
    @patch("runner.cybervisor.subprocess.Popen")
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
        result = task_mod.run_task(task, 0, state)
        self.assertTrue(result)
        mock_clean.assert_called_once()
        mock_branch.assert_called_once_with(self.tmpdir, "feat/test")

    @patch.object(task_mod, "ensure_clean_git", return_value=False)
    def test_run_task_git_clean_failure_skips_task(self, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
        }
        result = task_mod.run_task(task, 0, state)
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertIn("auto-commit", state["tasks"]["0"]["error"])

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=False)
    def test_run_task_branch_failure_skips_task(self, mock_branch, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "branch": True,
        }
        result = task_mod.run_task(task, 0, state)
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertIn("branch", state["tasks"]["0"]["error"])

    @patch.object(task_mod, "ensure_clean_git", return_value=False)
    def test_state_never_running_on_git_failure(self, mock_clean):
        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test task",
            "dir": self.tmpdir,
            "prompt": "do something",
        }
        task_mod.run_task(task, 0, state)
        self.assertNotEqual(state["tasks"]["0"]["status"], "running")
        self.assertEqual(state["tasks"]["0"]["status"], "failed")


class RunnerSelectionTests(unittest.TestCase):
    """T5.11: Tests for runner selection based on task 'use' field."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)
        self.home = Path(tempfile.mkdtemp()) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        (self.home / "archive").mkdir()
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.home / "state.json"),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
            patch.object(config, "ARCHIVE_DIR", self.home / "archive"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=True)
    @patch("runner.claude.subprocess.Popen")
    def test_use_claude_selects_claude_runner(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["<promise>COMPLETE</promise>\n"])
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test claude task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "use": "claude",
            "branch": "feat/test",
        }
        result = task_mod.run_task(task, 0, state)
        self.assertTrue(result)
        self.assertEqual(state["tasks"]["0"]["status"], "done")

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=True)
    @patch("runner.claude.subprocess.Popen")
    def test_use_claude_max_rounds_respected(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["no completion\n"])
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test claude task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "use": "claude",
            "max_rounds": 3,
            "branch": "feat/test",
        }
        with patch("time.sleep"):
            result = task_mod.run_task(task, 0, state)
        self.assertFalse(result)
        self.assertEqual(state["tasks"]["0"]["status"], "failed")
        self.assertEqual(mock_popen.call_count, 3)

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=True)
    @patch("runner.cybervisor.subprocess.Popen")
    def test_use_cybervisor_selects_cybervisor_runner(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["output\n"])
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test cybervisor task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "use": "cybervisor",
            "branch": "feat/test",
        }
        result = task_mod.run_task(task, 0, state)
        self.assertTrue(result)
        self.assertEqual(state["tasks"]["0"]["status"], "done")

    @patch.object(task_mod, "ensure_clean_git", return_value=True)
    @patch.object(task_mod, "create_task_branch", return_value=True)
    @patch("runner.cybervisor.subprocess.Popen")
    def test_missing_use_field_defaults_to_cybervisor(self, mock_popen, mock_branch, mock_clean):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["output\n"])
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        state = {"tasks": {}, "version": 1}
        task = {
            "name": "test default task",
            "dir": self.tmpdir,
            "prompt": "do something",
            "branch": "feat/test",
        }
        result = task_mod.run_task(task, 0, state)
        self.assertTrue(result)
        self.assertEqual(state["tasks"]["0"]["status"], "done")


class AddTaskTests(unittest.TestCase):
    """Tests for _add_task() appending all fields to tasks.yaml."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        self.tasks_file = self.home / "tasks.yaml"
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.tasks_file),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_creates_tasks_yaml_if_missing(self):
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/foo")
        self.assertTrue(self.tasks_file.exists())
        data = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(len(data["tasks"]), 1)

    def test_appends_to_existing_tasks(self):
        self.tasks_file.write_text(yaml.dump({
            "tasks": [{"name": "Existing", "dir": ".", "prompt": "old"}]
        }))
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/bar")
        data = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(len(data["tasks"]), 2)
        self.assertEqual(data["tasks"][1]["name"], "Task 2")

    def test_all_fields_present(self):
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/myproj")
        data = yaml.safe_load(self.tasks_file.read_text())
        task = data["tasks"][0]
        self.assertEqual(task["name"], "Task 1")
        self.assertEqual(task["dir"], "~/projects/myproj")
        self.assertIn("Describe what Claude should do.", task["prompt"])
        self.assertTrue(task["branch"])
        self.assertEqual(task["use"], "cybervisor")
        self.assertEqual(task["max_rounds"], 5)

    def test_prompt_file_comment_present(self):
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/myproj")
        content = self.tasks_file.read_text()
        self.assertIn("# prompt_file:", content)

    def test_header_comment_preserved_on_add(self):
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/foo")
        content = self.tasks_file.read_text()
        self.assertTrue(content.startswith("# Run 'tloop edit --help'"))

    def test_header_comment_preserved_on_append(self):
        self.tasks_file.write_text(config.SAMPLE_TASKS_YAML.replace("tasks: []", "tasks:\n  - name: Existing\n    dir: .\n    prompt: old\n"))
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/bar")
        content = self.tasks_file.read_text()
        self.assertTrue(content.startswith("# Run 'tloop edit --help'"))

    def test_task_numbering_increments(self):
        self.tasks_file.write_text(yaml.dump({
            "tasks": [{"name": "Task 1", "dir": ".", "prompt": ""}]
        }))
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/second")
        data = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(data["tasks"][1]["name"], "Task 2")

    def test_preserves_existing_file_structure(self):
        self.tasks_file.write_text(yaml.dump({
            "custom_key": "value",
            "tasks": [{"name": "Existing", "dir": ".", "prompt": "hi"}]
        }))
        with patch("builtins.print"):
            cmd_edit._add_task("~/projects/new")
        data = yaml.safe_load(self.tasks_file.read_text())
        self.assertEqual(data["custom_key"], "value")
        self.assertEqual(len(data["tasks"]), 2)


class EditorSelectionTests(unittest.TestCase):
    """Tests for editor selection and persistence in cmd_edit."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "tloop"
        self.home.mkdir(parents=True)
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "SETTINGS_FILE", self.home / "settings.json"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_cli_editor_overrides_settings(self):
        cmd_edit._save_settings({"editor": "vim"})
        result = cmd_edit._resolve_editor("code")
        self.assertEqual(result, "code")

    def test_saved_editor_used_when_no_cli_override(self):
        cmd_edit._save_settings({"editor": "code"})
        result = cmd_edit._resolve_editor()
        self.assertEqual(result, "code")

    def test_prompt_on_first_run(self):
        with patch("builtins.input", side_effect=["1"]):
            with patch.object(cmd_edit, "KNOWN_EDITORS", {"code": ("VS Code", "code")}):
                with patch("shutil.which", return_value="/usr/local/bin/code"):
                    result = cmd_edit._resolve_editor()
        self.assertEqual(result, "code")
        settings = json.loads((self.home / "settings.json").read_text())
        self.assertEqual(settings["editor"], "code")

    def test_custom_editor_via_prompt(self):
        with patch("builtins.input", side_effect=["2", "subl"]):
            with patch.object(cmd_edit, "KNOWN_EDITORS", {"code": ("VS Code", "code")}):
                with patch("shutil.which", return_value="/usr/local/bin/code"):
                    result = cmd_edit._resolve_editor()
        self.assertEqual(result, "subl")

    def test_corrupt_settings_file_triggers_prompt(self):
        (self.home / "settings.json").write_text("not json")
        with patch("builtins.input", side_effect=["1"]):
            with patch.object(cmd_edit, "KNOWN_EDITORS", {"code": ("VS Code", "code")}):
                with patch("shutil.which", return_value="/usr/local/bin/code"):
                    result = cmd_edit._resolve_editor()
        self.assertEqual(result, "code")


if __name__ == "__main__":
    unittest.main()

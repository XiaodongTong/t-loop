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
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_creates_directories(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "logs").mkdir(exist_ok=True)
        self.assertTrue(self.home.exists())
        self.assertTrue((self.home / "logs").exists())

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
        (self.home / "tasks.yaml").write_text("tasks:\n  - name: test\n    prompt: hi\n")
        config.ensure_tloop_home()
        content = (self.home / "tasks.yaml").read_text()
        self.assertIn("test", content)


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


class RunTaskGitIntegrationTests(unittest.TestCase):
    """T5.10: Updated existing tests — now uses TLOOP_HOME paths."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _init_git_repo(self.tmpdir)
        self.home = Path(tempfile.mkdtemp()) / "tloop"
        self.home.mkdir(parents=True)
        (self.home / "logs").mkdir()
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.home / "state.json"),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
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
        self.patches = [
            patch.object(config, "TLOOP_HOME", self.home),
            patch.object(config, "TASKS_FILE", self.home / "tasks.yaml"),
            patch.object(config, "STATE_FILE", self.home / "state.json"),
            patch.object(config, "LOGS_DIR", self.home / "logs"),
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

# Plan 04: PyPI 发布 + 子命令重构

## 目标

1. 项目发布到 PyPI，用户 `pip install t-loop` 后使用 `tloop` 命令
2. 增加 `-v`/`--version` 和 `-h`/`--help`
3. 增加子命令 `run`、`edit`
4. 代码结构为支持多种 runner（cybervisor / claude code）预留扩展点

---

## 一、目录结构变更

### 现状

```
src/
  main.py            # 入口，调用 cli.main()
  cli.py             # 所有 CLI 逻辑 + 任务执行 + 归档（600+ 行，职责过多）
  git_ops.py         # git 操作
  claude_runner.py   # claude CLI wrapper（实际用于 auto-commit）
```

### 目标

```
src/
  main.py            # 入口函数 main()，只做 argparse 路由
  config.py          # TLOOP_HOME 路径常量、配置加载/保存（从 cli.py 提取）
  state.py           # state.json 读写、归档逻辑（从 cli.py 提取）
  task.py            # 单任务执行流程 run_task()（从 cli.py 提取）
  cmd_run.py         # tloop run 子命令（任务循环、状态展示）
  cmd_edit.py        # tloop edit 子命令
  cmd_migrate.py     # tloop migrate 子命令（从 cli.py 提取）
  cmd_archive.py     # tloop archive 子命令（从 cli.py 提取）
  git_ops.py         # git 操作（不变）
  runner/            # runner 扩展点（唯一子目录）
    __init__.py      # Runner 基类
    cybervisor.py    # 现有 cybervisor 执行逻辑（从 cli.py 提取 subprocess 调用）
    claude.py        # claude code runner（本次不实现，占位）
```

### 变更理由

| 变更 | 理由 |
|------|------|
| `cli.py` 拆分为 6 个文件 | 600+ 行承担了配置、状态、归档、迁移、任务执行、CLI 解析，职责过多 |
| 保持 `src/` flat + 唯一子目录 `runner/` | 只有 runner 是明确的扩展边界，其余模块 flat 即可，避免无意义嵌套 |
| `runner/` 子目录 + 基类 | 为 cybervisor / claude code 两种执行方式预留扩展点 |

---

## 二、各需求实现方案

### 需求 1：PyPI 发布

#### pyproject.toml 调整

```toml
[project]
name = "t-loop"
version = "0.4.0"
description = "Automated Claude Code task runner"
readme = "README.md"
requires-python = ">=3.9"
license = "MIT"
dependencies = [
    "pyyaml>=6.0",
]

[project.scripts]
tloop = "main:main"

[tool.setuptools]
package-dir = {"" = "src"}
py-modules = ["main", "config", "state", "task", "cmd_run", "cmd_edit", "cmd_migrate", "cmd_archive", "git_ops"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["runner*"]

[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"
```

关键点：
- 保持 `package-dir = {"" = "src"}` + `py-modules`（flat 模块）
- `runner` 包通过 `packages.find` 自动发现
- entry point：`tloop = "main:main"`
- 命令名 `t-loop` → `tloop`

#### `src/main.py` 顶部定义版本号

```python
__version__ = "0.4.0"
```

#### README.md 新增发布/安装说明

**开发者发布：**

```bash
pip install build twine
python -m build          # 构建 sdist + wheel
twine check dist/*       # 检查包
twine upload dist/*      # 发布到 PyPI
# 测试 PyPI: twine upload --repository testpypi dist/*
```

**本地调试：**

```bash
pip install -e .         # 可编辑安装，修改即时生效
tloop --help             # 验证命令可用
```

**用户安装/更新：**

```bash
pip install t-loop       # 安装
pip install --upgrade t-loop  # 更新
```

---

### 需求 2：`-v`/`--version` 和 `-h`/`--help`

`-h` 由 argparse 自动提供。`-v` 需手动添加：

```python
# src/main.py
def main():
    parser = argparse.ArgumentParser(
        prog="tloop",
        description="t-loop: Automated Claude Code task runner",
    )
    parser.add_argument("-v", "--version", action="version",
                        version=f"tloop {__version__}")
    # ... subcommands ...
```

效果：

```
$ tloop -v
tloop 0.4.0

$ tloop -h
usage: tloop [-h] [-v] {run,edit,migrate,archive} ...

t-loop: Automated Claude Code task runner

positional arguments:
  {run,edit,migrate,archive}

options:
  -h, --help       show this help message and exit
  -v, --version    show version and exit
```

---

### 需求 3：子命令

#### 整体命令结构

```
tloop run [OPTIONS]          # 执行任务（原 t-loop 的默认行为）
tloop edit                   # 用 $EDITOR 打开 ~/.tloop/tasks.yaml
tloop edit -h                # 输出 tasks.yaml 格式说明
tloop migrate                # 迁移旧数据（原 tloop migrate）
tloop archive [--latest]     # 查看归档（原 tloop --archive）
```

#### 3.1 `tloop run`（`cmd_run.py`）

```python
def add_parser(subparsers):
    p = subparsers.add_parser("run", help="Run tasks defined in ~/.tloop/tasks.yaml")
    p.add_argument("--status", "-s", action="store_true")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--only", type=int, help="Run only task #N (1-based)")
    p.add_argument("--confirm", "-i", action="store_true")
    p.add_argument("--continue", "-c", dest="continue_on_fail", action="store_true")
    p.set_defaults(func=handle)

def handle(args):
    # 原 cli.main() 中的任务循环逻辑
```

#### 3.2 `tloop edit`（`cmd_edit.py`）

```python
def add_parser(subparsers):
    p = subparsers.add_parser("edit", help="Open ~/.tloop/tasks.yaml in editor")
    p.set_defaults(func=handle)

def handle(args):
    import os, subprocess
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(TASKS_FILE)])
```

`tloop edit -h` 输出格式说明（写在 parser 的 description 中）：

```
$ tloop edit -h
usage: tloop edit [-h]

Open ~/.tloop/tasks.yaml in your editor ($EDITOR, defaults to vi).

Task file format (~/.tloop/tasks.yaml):

  defaults:
    model: opus              # optional default model

  tasks:
    - name: My task
      dir: ~/projects/my-project
      prompt: |
        Describe what Claude should do.
      # OR:
      prompt_file: ./prompts/my-task.md
      model: opus            # optional override
      branch: true           # true=auto, "custom/name", false=skip

  Each task runs in the specified directory. Completed tasks are
  archived to ~/.tloop/archive/ after each run cycle.
```

---

### 需求 4：Runner 扩展点

#### `src/runner/__init__.py`

```python
from abc import ABC, abstractmethod

class Runner(ABC):
    @abstractmethod
    def run(self, prompt: str, cwd: str, model: str = None) -> int:
        """Run a task. Returns exit code (0=success)."""
        ...
```

#### `src/runner/cybervisor.py`

```python
from runner import Runner
import subprocess

class CybervisorRunner(Runner):
    def run(self, prompt, cwd, model=None):
        cmd = ["cybervisor", "run", prompt]
        if model:
            cmd.extend(["--model", model])
        proc = subprocess.Popen(cmd, cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            print(line, end="")
        proc.wait()
        return proc.returncode
```

#### `src/runner/claude.py`

```python
from runner import Runner

class ClaudeRunner(Runner):
    """Claude Code runner (placeholder)."""
    def run(self, prompt, cwd, model=None):
        raise NotImplementedError("Claude Code runner not yet implemented")
```

#### `task.py` 中使用 runner

```python
from runner.cybervisor import CybervisorRunner

def run_task(task, index, state, defaults):
    # ... git safety, branch setup ...

    runner = CybervisorRunner()  # future: select based on config
    returncode = runner.run(prompt, dir_path, model=model)

    # ... update state based on returncode ...
```

后续增加 claude code runner 只需：
1. 实现 `ClaudeRunner.run()`
2. 在 config 中增加 `runner: claude` 选项
3. `task.py` 中根据配置选择 runner

---

## 三、迁移影响

### `cli.py` 拆分映射

| cli.py 中的内容 | 迁移到 |
|-----------------|--------|
| `TLOOP_HOME`, `TASKS_FILE` 等路径常量 | `config.py` |
| `load_config()`, `ensure_tloop_home()` | `config.py` |
| `load_state()`, `save_state()` | `state.py` |
| `archive_completed_tasks()`, `show_archives()` | `state.py` + `cmd_archive.py` |
| `run_task()` | `task.py` |
| `resolve_prompt_file()` | `task.py` |
| `run_migrate()` | `cmd_migrate.py` |
| `show_status()`, `main()` | `cmd_run.py` |
| 颜色常量 `GREEN` 等 | 各使用模块各自定义，或提取到 `config.py` |

### 测试迁移要点

- `import cli` → `import config` / `import state` / `import task` 等
- `patch("git_ops.run_claude")` → `patch("runner.claude_runner.run_claude")` 或按新 runner 类 patch
- `patch.object(cli, "TLOOP_HOME", ...)` → `patch.object(config, "TLOOP_HOME", ...)`
- 确保 `python -m pytest test/ -v` 全部通过

### 向后兼容

- `~/.tloop/tasks.yaml` 格式不变
- `~/.tloop/state.json` 格式不变
- 旧的 `t-loop --status` 等参数移到 `tloop run --status`

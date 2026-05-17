# 方案：t-loop CLI 工程化改造

## 背景

当前 t-loop 以 `python t-loop.py` 方式运行，存在以下问题：

1. **无法全局使用** — 必须在项目目录下运行，或写完整路径
2. **入口文件冗余** — `t-loop.py` 只是转发到 `tloop.cli.main()`，多了一层间接
3. **无标准包管理** — 没有 `pyproject.toml`，不支持 `pip install`
4. **硬编码路径** — `SCRIPT_DIR` 假设数据文件在代码目录下（与 [[plan02-data-home]] 的 `~/.tloop/` 迁移方案关联）

目标：改造为标准的 Python CLI 项目，`pip install` 后即可在任何位置使用 `t-loop` 命令。

---

## 阶段一：项目结构重组

### 改造后的目录结构

```
t-loop/                              # 项目根目录（开发仓库）
├── pyproject.toml                   # 包定义 + CLI 入口点
├── README.md
├── LICENSE
├── .gitignore
├── src/
│   └── core/                        # 源码包（import core）
│       ├── __init__.py              # 版本号等元信息
│       ├── cli.py                   # CLI 入口（argparse → main）
│       ├── config.py                # 路径管理、配置加载（从 cli.py 抽取）
│       ├── git_ops.py               # Git 操作（不变）
│       ├── claude_runner.py         # Claude 运行器（不变）
│       └── archive.py               # 归档逻辑（plan02 的阶段二）
├── test/
│   ├── test_cli.py
│   └── test_git_ops.py
├── docs/
│   └── plan/
└── tasks.example.yaml               # 示例文件（随包分发）
```

### 关键变化

| 变化 | 说明 |
|------|------|
| 删除 `t-loop.py` | 入口点由 `pyproject.toml` 的 `[project.scripts]` 注册 |
| `tloop/` → `src/core/` | 采用 src-layout，包名改为 `core` 避免与项目名 `t-loop` 混淆 |
| 新增 `config.py` | 从 `cli.py` 抽取路径常量、YAML 加载、状态管理等配置相关逻辑 |
| 新增 `archive.py` | 归档逻辑独立模块（对应 plan02） |
| `tasks.yaml` → `tasks.example.yaml` | 仓库中只保留示例，运行时从 `~/.tloop/tasks.yaml` 读取 |

---

## 阶段二：pyproject.toml 配置

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "t-loop"
version = "0.3.0"
description = "Automated Claude Code task runner"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
    "pyyaml>=6.0",
]

[project.scripts]
t-loop = "core.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
tloop = ["../tasks.example.yaml"]  # 虽然包名是 core，setuptools 用目录名
```

### `[project.scripts]` 说明

```
t-loop = "core.cli:main"
```

- 左边 `t-loop`：注册的全局命令名
- 右边 `core.cli:main`：包路径.模块:函数
- `pip install` 后自动在 `~/.local/bin/`（或 venv 的 `bin/`）生成 `t-loop` 可执行脚本

---

## 阶段三：代码改动

### 3.1 入口文件 t-loop.py → 删除

当前 `t-loop.py` 内容：

```python
from core.cli import main
if __name__ == "__main__":
    main()
```

改为由 `pyproject.toml` 的 `[project.scripts]` 自动生成入口脚本，无需手动维护。

> 如果仍想支持 `python -m core` 方式运行，可在 `src/core/__main__.py` 中添加：
> ```python
> from core.cli import main
> main()
> ```

### 3.2 cli.py 路径常量重构

```python
# 之前（基于项目目录）
SCRIPT_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = SCRIPT_DIR / "tasks.yaml"
STATE_FILE = SCRIPT_DIR / ".tloop-state.json"
LOGS_DIR = SCRIPT_DIR / "logs"

# 之后（基于 ~/.tloop 数据目录）
TLOOP_HOME = Path.home() / ".tloop"
TASKS_FILE = TLOOP_HOME / "tasks.yaml"
STATE_FILE = TLOOP_HOME / "state.json"
LOGS_DIR = TLOOP_HOME / "logs"
ARCHIVE_DIR = TLOOP_HOME / "archive"
EXAMPLE_FILE = Path(__file__).resolve().parent.parent / "tasks.example.yaml"
```

> 此改动与 plan02 的阶段一一致，此处一并纳入。

### 3.3 跨模块 import 更新

所有 `from tloop.xxx import ...` 改为 `from core.xxx import ...`：

```python
# cli.py
from core.config import load_config, load_state, save_state, ...
from core.git_ops import ensure_clean_git, create_task_branch

# git_ops.py
from core.claude_runner import run_claude
```

### 3.4 新增 config.py（从 cli.py 抽取）

将以下函数从 `cli.py` 迁入 `config.py`：

| 函数 | 说明 |
|------|------|
| `ensure_tloop_home()` | 确保 `~/.tloop/` 目录结构存在 |
| `ensure_yaml()` | 自动安装 pyyaml（有了 pyproject.toml 后可简化为直接 import） |
| `load_config()` | 加载 tasks.yaml |
| `load_state()` / `save_state()` | 状态文件读写 |
| 路径常量 | `TLOOP_HOME`, `TASKS_FILE`, `STATE_FILE`, `LOGS_DIR`, `ARCHIVE_DIR` |

`cli.py` 只保留 CLI 参数解析和任务执行逻辑，通过 `from core.config import ...` 引入配置。

### 3.5 ensure_yaml 简化

有了 `pyproject.toml` 声明 `pyyaml` 为依赖后，`ensure_yaml()` 的动态安装逻辑可以去掉：

```python
# config.py
import yaml  # 不再需要 try/except

def load_config():
    if not TASKS_FILE.exists():
        print(f"Error: {TASKS_FILE} not found")
        print(f"Run 't-loop init' to create an example config.")
        sys.exit(1)
    with open(TASKS_FILE) as f:
        return yaml.safe_load(f) or {}
```

### 3.6 新增 init 子命令

```python
def cmd_init():
    """首次使用时创建 ~/.tloop/ 目录结构和示例 tasks.yaml"""
    ensure_tloop_home()
    if TASKS_FILE.exists():
        print(f"~/.tloop/tasks.yaml already exists.")
        return
    # 复制示例文件
    if EXAMPLE_FILE.exists():
        import shutil
        shutil.copy2(EXAMPLE_FILE, TASKS_FILE)
    else:
        TASKS_FILE.write_text(DEFAULT_TASKS_YAML)
    print(f"Created {TASKS_FILE}")
    print(f"Edit it and run 't-loop' to start.")
```

### 3.7 CLI 参数改为子命令结构

```python
def main():
    parser = argparse.ArgumentParser(
        prog="t-loop",
        description="Automated Claude Code task runner",
    )
    sub = parser.add_subparsers(dest="command")

    # 默认行为：运行任务（无子命令时）
    parser.add_argument("--status", "-s", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--only", type=int)
    parser.add_argument("--confirm", "-i", action="store_true")
    parser.add_argument("--continue", "-c", dest="continue_on_fail", action="store_true")

    # 子命令
    sub.add_parser("init", help="Initialize ~/.tloop/ config")
    sub.add_parser("status", aliases=["-s"], help="Show task status")

    archive_parser = sub.add_parser("archive", help="Manage archived tasks")
    archive_parser.add_argument("action", nargs="?", default="list", choices=["list", "latest"])
    ...
```

向后兼容：无子命令时保持原有行为（运行任务），原有 `-s`, `--reset` 等参数继续可用。

---

## 阶段四：安装与分发

### 开发模式安装（推荐开发时使用）

```bash
# 在项目根目录执行
pip install -e .

# 之后可在任何位置运行
t-loop
t-loop --status
t-loop init
```

### 正式安装

```bash
pip install .
```

### 后续：发布到 PyPI（可选）

```bash
pip install build twine
python -m build
twine upload dist/*
```

之后用户可以：

```bash
pip install t-loop
```

---

## 完整改动清单

| 文件 | 改动 |
|------|------|
| **新增** `pyproject.toml` | 包定义、依赖、CLI 入口点 |
| **新增** `src/core/__init__.py` | 版本号元信息 |
| **新增** `src/core/__main__.py` | 支持 `python -m core` |
| **新增** `src/core/config.py` | 从 cli.py 抽取配置/路径/状态管理 |
| **新增** `src/core/archive.py` | 归档逻辑（plan02） |
| **移动** `tloop/cli.py` → `src/core/cli.py` | 移入 src 目录，引用 config 模块 |
| **移动** `tloop/git_ops.py` → `src/core/git_ops.py` | 移入 src 目录，无逻辑改动 |
| **移动** `tloop/claude_runner.py` → `src/core/claude_runner.py` | 移入 src 目录，无逻辑改动 |
| **删除** `t-loop.py` | 入口点由 pyproject.toml 注册 |
| **删除** `tloop/` | 旧包目录，内容已移入 `src/core/` |
| **重命名** `tasks.yaml` → `tasks.example.yaml` | 仓库中只保留示例 |
| **更新** `.gitignore` | 移除 `.tloop-state.json`（不再在项目目录生成） |
| **更新** `README.md` | 更新安装和使用说明 |

---

## 实施顺序

建议按以下顺序分步实施，每步可独立验证：

### 第一步：基础 CLI 化（最小可行）
1. 创建 `pyproject.toml`
2. 创建 `src/core/` 目录，移动代码
3. 删除 `t-loop.py`
4. `pip install -e .` 验证 `t-loop` 命令可用

### 第二步：数据目录迁移（与 plan02 合并）
1. 新增 `config.py`，路径常量指向 `~/.tloop/`
2. 新增 `ensure_tloop_home()` 和 `cmd_init()`
3. 首次运行自动初始化

### 第三步：子命令与归档
1. argparse 改为子命令结构
2. 新增 `archive` 子命令
3. 归档逻辑实现

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| src-layout 导致 import 路径变化 | `pip install -e .` 后 `import core` 正常工作，测试验证 |
| 用户已有 `~/.tloop/` 目录 | `init` 命令检测并跳过，不覆盖 |
| 开发时不方便测试 | `pip install -e .` 开发模式，代码改动即时生效 |
| 旧用户习惯 `python t-loop.py` | README 中说明新用法；可选保留 `__main__.py` 支持 `python -m core` |

## 依赖关系

本方案（plan03）的第二步与 [[plan02-data-home]] 高度重叠，建议合并实施：
- plan03 第一步（基础 CLI 化）独立，可先做
- plan03 第二步 = plan02 阶段一（数据目录迁移），二合一
- plan03 第三步 = plan02 阶段二（归档），二合一

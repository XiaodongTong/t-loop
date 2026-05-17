# 方案：数据目录迁移至 ~/.tloop 及任务归档

## 背景

当前 t-loop 的数据文件（tasks.yaml、.tloop-state.json、logs/）全部存放在项目目录下，存在两个问题：

1. **数据与代码混杂** — 任务定义、运行状态、日志散落在代码仓库中，容易被误提交、误清理
2. **重复执行** — 已完成的任务仍然留在 tasks.yaml 中，虽然 state 会跳过 done 状态的任务，但任务越积越多，管理混乱

---

## 阶段一：数据目录迁移至 ~/.tloop

### 目标目录结构

```
~/.tloop/
├── tasks.yaml              # 任务定义（用户编辑入口）
├── state.json              # 运行状态
├── config.yaml             # 全局配置（可选，后续扩展）
├── logs/                   # 执行日志
│   ├── 001-blink.log
│   └── 002-t-loop.log
└── archive/                # 已完成任务的归档
    ├── run-20260517-083000.yaml
    └── run-20260517-143000.yaml
```

### 改动点

#### 1. 路径常量调整（cli.py）

```python
# 之前
SCRIPT_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = SCRIPT_DIR / "tasks.yaml"
STATE_FILE = SCRIPT_DIR / ".tloop-state.json"
LOGS_DIR = SCRIPT_DIR / "logs"

# 之后
TLOOP_HOME = Path.home() / ".tloop"
TASKS_FILE = TLOOP_HOME / "tasks.yaml"
STATE_FILE = TLOOP_HOME / "state.json"
LOGS_DIR = TLOOP_HOME / "logs"
ARCHIVE_DIR = TLOOP_HOME / "archive"
```

#### 2. 首次运行自动初始化

```python
def ensure_tloop_home():
    """确保 ~/.tloop 目录结构存在"""
    TLOOP_HOME.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    if not TASKS_FILE.exists():
        # 生成示例 tasks.yaml，引导用户编辑
        TASKS_FILE.write_text(EXAMPLE_TASKS_YAML)
        print(f"已创建 {TASKS_FILE}，请编辑后重新运行")
        sys.exit(0)
```

#### 3. tasks.yaml 中的 `dir` 字段语义不变

任务中的 `dir` 指向目标项目路径（即 Claude 执行任务的目录），与数据存储位置无关：

```yaml
tasks:
  - name: blink
    dir: ~/workingspace/blink    # Claude 工作目录
    prompt: < ./docs/plan/p1-enhancement.md
```

> 注意：`prompt_file` 的相对路径基准应改为 `~/.tloop/` 或改为仅支持绝对路径。建议 `prompt_file` 支持 `~` 展开，并优先从 `~/.tloop/` 解析相对路径。

#### 4. 迁移脚本（可选）

提供一次性迁移命令，将项目目录下的旧数据移到 `~/.tloop/`：

```bash
python -m tloop migrate
```

逻辑：
- 如果 `~/.tloop/` 已存在且有 tasks.yaml → 提示冲突，跳过
- 否则复制 `tasks.yaml`、`.tloop-state.json`、`logs/` → `~/.tloop/`
- 迁移完成后提示用户确认

---

## 阶段二：任务归档

### 核心思路

全部任务执行完成后，将已完成的任务从 `tasks.yaml` 中移除，转存到 `archive/` 下的归档文件。这样 `tasks.yaml` 始终只保留待执行的任务。

### 执行流程

```
任务执行完毕
    ↓
检查 state.json：是否所有任务都已完成？
    ↓ (是)
    ① 生成归档文件：archive/run-YYYYMMDD-HHMMSS.yaml
    ② 将已完成任务的定义 + 执行状态写入归档
    ③ 从 tasks.yaml 中移除已完成的任务
    ④ 清空 state.json
    ↓ (否)
保持原样，下次运行时继续未完成的任务
```

### 归档文件格式

`archive/run-20260517-083000.yaml`：

```yaml
archived_at: "2026-05-17T08:30:00"
run_summary:
  total: 3
  done: 2
  failed: 1
tasks:
  - name: blink
    dir: ~/workingspace/blink
    prompt: < ./docs/plan/p1-enhancement.md
    result:
      status: done
      started_at: "2026-05-17T08:10:10"
      finished_at: "2026-05-17T08:25:33"

  - name: t-loop
    dir: ~/workingspace/t-loop
    prompt: < ./docs/plan/plan01-git.md
    result:
      status: failed
      started_at: "2026-05-17T08:25:40"
      finished_at: "2026-05-17T08:30:00"
      returncode: 1
```

### 归档逻辑（伪代码）

```python
def archive_completed_tasks(config, state):
    """将已完成的任务归档，从 tasks.yaml 中移除"""
    tasks = config.get("tasks", [])
    task_states = state.get("tasks", {})

    # 分离：已完成 vs 未完成
    completed = []
    remaining = []
    for i, task in enumerate(tasks):
        ts = task_states.get(str(i), {})
        if ts.get("status") == "done":
            completed.append({**task, "result": ts})
        else:
            remaining.append(task)

    if not completed:
        return  # 没有已完成的，不需要归档

    # 写入归档文件
    now = datetime.now()
    archive_name = f"run-{now.strftime('%Y%m%d-%H%M%S')}.yaml"
    archive_path = ARCHIVE_DIR / archive_name

    archive_data = {
        "archived_at": now.isoformat(),
        "run_summary": {
            "total": len(tasks),
            "done": len(completed),
            "failed": sum(1 for t in completed if t.get("result", {}).get("status") == "failed"),
        },
        "tasks": completed,
    }
    write_yaml(archive_path, archive_data)

    # 更新 tasks.yaml：只保留未完成的任务
    config["tasks"] = remaining
    write_yaml(TASKS_FILE, config)

    # 清空 state
    save_state({"tasks": {}, "version": 1})

    print(f"已归档 {len(completed)} 个已完成任务 → {archive_path}")
```

### 归档触发时机

在 `main()` 函数的执行循环结束后调用：

```python
def main():
    # ... 执行任务循环 ...

    # 全部执行完毕后，尝试归档
    archive_completed_tasks(config, state)
```

**只在全部任务跑完一轮后才归档**，不逐个任务归档。原因：
- 保持 tasks.yaml 稳定，执行期间不修改
- 归档是批量操作，逻辑简单
- 如果中途失败，tasks.yaml 保留全部任务定义，下次可以继续

### 查看归档

新增 CLI 命令：

```bash
t-loop --archive          # 列出所有归档文件
t-loop --archive latest   # 显示最近一次归档的详情
```

---

## 完整改动清单

| 文件 | 改动 |
|------|------|
| `tloop/cli.py` | 路径常量改为 `~/.tloop`；新增 `ensure_tloop_home()`、`archive_completed_tasks()`；新增 `--archive` 参数 |
| `tloop/__init__.py` | 无改动 |
| `tloop/git_ops.py` | 无改动（操作的是任务目录，不涉及数据目录） |
| `tloop/claude_runner.py` | 无改动 |
| 项目根目录 `tasks.yaml` | 迁移至 `~/.tloop/tasks.yaml`（可保留示例文件在仓库中） |
| 项目根目录 `.tloop-state.json` | 迁移至 `~/.tloop/state.json`，之后可删除 |
| 项目根目录 `logs/` | 迁移至 `~/.tloop/logs/`，之后可删除 |

## 风险与应对

| 风险 | 应对 |
|------|------|
| `~/.tloop/tasks.yaml` 被误删 | 归档文件保留了完整的任务定义，可以从归档恢复 |
| 迁移后项目根目录的旧文件残留 | `migrate` 命令迁移后提示删除，或 `.gitignore` 中忽略 |
| 归档文件越来越多 | 可后续增加 `--archive clean --before 2026-01-01` 清理旧归档 |
| `prompt_file` 相对路径基准变化 | 文档中说明，或支持从原项目目录解析相对路径 |
| 部分完成部分失败时的归档行为 | 只归档 status=done 的任务，failed 的保留在 tasks.yaml 中等待重试 |

## 后续可选增强

- `config.yaml` — 全局默认 model、并发数等配置
- `--archive restore <file>` — 从归档恢复任务到 tasks.yaml
- 归档自动清理策略 — 保留最近 N 次归档

# t-loop

自动化 Claude Code 任务运行器。用 YAML 定义任务，t-loop 按顺序执行，自带 git 安全保护。

## 安装

```bash
pip install tloop-cli           # 从 PyPI 安装
pip install -e .                # 本地开发安装
```

需要 Python >=3.9，唯一外部依赖：`pyyaml`。

## 快速开始

```bash
# 首次运行会创建 ~/.tloop/tasks.yaml 示例配置
tloop run

# 编辑任务后运行
tloop edit
tloop run
```

## 任务配置

编辑 `~/.tloop/tasks.yaml`：

```yaml
tasks:
  - name: 我的第一个任务
    dir: ~/projects/my-project
    prompt: |
      描述 Claude 应该做什么。

  - name: 使用 prompt 文件的任务
    dir: ~/projects/my-project
    prompt_file: ./prompts/my-task.md
    branch: feat/login   # 自定义分支名
```

### 任务字段

| 字段 | 说明 |
|-------|-------------|
| `name` | 任务显示名称 |
| `dir` | 任务工作目录 |
| `prompt` | 内联 prompt 文本 |
| `prompt_file` | prompt 文件路径（解析顺序：绝对路径 → `~/.tloop/` 相对 → 任务目录相对） |
| `model` | 覆盖该任务的模型 |
| `branch` | `true`（自动 `feature-YYYYMMDD-NNN`）、`"custom/name"`、或 `false`（跳过分支） |

## 用法

```bash
tloop run                  # 运行所有待执行任务
tloop run --status         # 查看任务状态
tloop run --only 2         # 只运行第 2 个任务
tloop run --confirm        # 每个任务前确认
tloop run -c               # 失败后继续执行
tloop run --reset          # 重置所有任务为待执行
tloop edit                 # 用 $EDITOR 打开 tasks.yaml
tloop archive              # 列出归档记录
tloop archive --latest     # 显示最近一次归档详情
tloop migrate              # 迁移旧的项目本地数据到 ~/.tloop/
```

## 工作原理

每个任务的执行流程：

1. **自动提交** — 如果工作目录有未提交的更改，t-loop 会用 Claude 先提交暂存区内容，再提交剩余更改。敏感文件（.env、密钥等）会被排除。
2. **创建分支** — 创建任务分支（默认 `feature-YYYYMMDD-NNN`）隔离更改。
3. **执行任务** — 在目标目录运行 `cybervisor run <prompt>`。
4. **归档** — 已完成的任务移至 `~/.tloop/archive/`，并从 `tasks.yaml` 中移除。

## 文件位置

```
~/.tloop/
├── tasks.yaml      # 任务定义
├── state.json      # 运行时状态（任务状态）
├── logs/           # 执行日志
└── archive/        # 已完成任务的归档
```

## 开发

```bash
pip install -e .
python -m pytest test/ -v
```

## 许可证

MIT

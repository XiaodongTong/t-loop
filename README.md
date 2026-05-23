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
| `use` | 任务执行器：`cybervisor`（默认，多阶段复杂任务）或 `claude`（定向任务，支持循环） |
| `max_rounds` | `use: claude` 时生效，最大迭代次数（默认 5）；到达上限前未收到 `<promise>COMPLETE</promise>` 信号则任务失败 |

## 用法

```bash
tloop run                  # 运行所有待执行任务
tloop run --status         # 查看任务状态
tloop run --only 2         # 只运行第 2 个任务
tloop run --confirm        # 每个任务前确认
tloop run -c               # 失败后继续执行
tloop run --reset          # 重置所有任务为待执行
tloop edit                 # 用 $EDITOR 打开 tasks.yaml
tloop edit ~/proj/xxx      # 快速添加一条完整任务（含 dir/branch/use/max_rounds），再打开编辑器
tloop log                  # 列出所有日志文件（任务编号、名称、大小、时间）
tloop log 3                # 查看第 3 个任务的日志
tloop log --follow         # 实时追踪最新日志（Ctrl+C 停止）
tloop log --search ERROR   # 搜索所有日志中的关键词（大小写不敏感）
tloop archive              # 列出归档记录
tloop archive --latest     # 显示最近一次归档详情
tloop migrate              # 迁移旧的项目本地数据到 ~/.tloop/
```

## 执行器

t-loop 支持两种任务执行器，通过 `use` 字段选择：

| 执行器 | 说明 | 适用场景 |
|--------|------|----------|
| `cybervisor` | 默认，执行 `cybervisor run`，适合复杂多阶段任务 | 大型重构、多步骤分析 |
| `claude` | 执行 `claude -p --dangerously-skip-permissions`，支持循环迭代 | 定向 bug 修复、明确目标的任务 |

### ClaudeRunner 循环机制

`use: claude` 时，任务以多轮迭代方式执行：

1. 每轮启动一次 `claude -p --dangerously-skip-permissions`，传入 prompt
2. 如果输出包含 `<promise>COMPLETE</promise>`，立即结束并标记成功
3. 否则等待 2 秒，继续下一轮，直到达到 `max_rounds`（默认 5）
4. `max_rounds` 用尽仍未检测到完成信号，任务标记失败

使用示例：

```yaml
tasks:
  - name: 修复空指针 bug
    dir: ~/proj
    use: claude
    max_rounds: 3
    prompt_file: bugfix.md
```

在 prompt 文件中加入 `<promise>COMPLETE</promise>` 即可让 Claude 主动退出循环。

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

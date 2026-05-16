# 方案：任务执行前的 Git 安全保护

## 背景

t-loop 在目标项目中执行任务前，项目可能存在未提交的代码改动。直接执行新任务会带来风险：
- 未提交的代码可能与新任务改动混合，难以区分和回滚
- 在错误的分支上工作，污染主分支

因此需要在执行任务前完成两件事：**提交未提交的代码** → **创建新分支**。

---

## 阶段一：自动提交未提交代码

### 执行流程

```
进入任务目录
    ↓
git status 检查
    ↓ (dirty)
调用 Claude 提交暂存区改动
    ↓
git status 检查
    ↓ (仍有改动)
调用 Claude 提交工作区改动
    ↓
git status 检查
    ↓ (clean)
进入阶段二
```

### 提交策略：Prompt 内嵌方式

**不依赖 `/commit` Skill**，而是在 t-loop.py 中生成一个专用的提交 prompt，与任务 prompt 分两次调用 Claude。

理由：
1. `/commit` Skill 是全局安装的，只在当前用户的设备上可用。t-loop 的目标用户可能没有这个 Skill。
2. 将 commit 逻辑内嵌到 prompt 中，不依赖任何外部 Skill，保证可移植性。
3. 分两次调用 Claude（先提交、再执行任务），职责清晰，互不干扰。

### 提交 Prompt 模板

**第一次调用**（提交暂存区）：

```
你是一个 Git 提交助手。请检查当前项目的 Git 状态：

1. 运行 `git status` 和 `git diff --cached --stat` 查看暂存区改动
2. 如果暂存区有改动：
   - 运行 `git diff --cached` 查看详细改动
   - 总结改动内容，生成中文 commit message（格式：<类型>: <描述>）
   - 类型包括：feat/fix/docs/style/refactor/perf/test/chore/ci/revert
   - 执行 `git commit`
3. 如果暂存区为空，无需操作
4. 最后运行 `git status` 确认结果

注意：不要提交工作区改动，只处理暂存区。不要使用 --no-verify。
```

**第二次调用**（提交工作区）：

```
你是一个 Git 提交助手。请检查当前项目的工作区改动：

1. 运行 `git status` 查看状态
2. 如果工作区有改动：
   - 运行 `git add -A` 暂存所有改动
   - 运行 `git diff --cached` 查看改动内容
   - 总结改动内容，生成中文 commit message（格式：<类型>: <描述>）
   - 执行 `git commit`
3. 如果工作区干净，无需操作
4. 最后运行 `git status` 确认结果

注意：不要使用 --no-verify。
```

### t-loop.py 中的实现逻辑（伪代码）

```python
def ensure_clean_git(dir_path):
    """确保目标项目工作区干净，否则自动提交"""
    if is_git_clean(dir_path):
        return True

    # 第一次：提交暂存区
    if has_staged_changes(dir_path):
        run_claude(dir_path, COMMIT_STAGED_PROMPT)

    # 第二次：提交工作区
    if not is_git_clean(dir_path):
        run_claude(dir_path, COMMIT_WORKDIR_PROMPT)

    # 验证
    if not is_git_clean(dir_path):
        log("警告：自动提交后工作区仍不干净，跳过此任务")
        return False
    return True

def is_git_clean(dir_path):
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=dir_path, capture_output=True, text=True
    )
    return result.stdout.strip() == ""
```

### 可行性评估

| 项目 | 评估 | 说明 |
|------|------|------|
| 检测 Git 状态 | ✅ 简单 | `git status --porcelain` 即可判断 |
| Claude 生成 commit message | ✅ 可行 | `claude -p` 可以读取 diff 并生成合理的中文 commit |
| 两次调用保证干净 | ✅ 可行 | 第一次处理暂存区，第二次处理工作区，逻辑清晰 |
| 敏感文件误提交 | ⚠️ 需注意 | prompt 中应提醒检查 .env / credentials 等，Claude 一般能识别 |
| 执行耗时 | ⚠️ 可接受 | 每次 commit 调用 Claude 约 10-30 秒，整体增加约 1 分钟 |

---

## 阶段二：分支管理

### tasks.yaml 新增字段

```yaml
tasks:
  - name: 修复登录超时
    dir: ~/projects/auth-service
    branch: true           # 默认值，自动生成分支名
    # branch: "feat/login" # 指定分支名
    # branch: false        # 不创建新分支，在当前分支工作
    prompt: |
      修复登录超时问题...
```

### 分支命名规则

| `branch` 配置 | 行为 | 示例 |
|---------------|------|------|
| 不配置 / `true` | 自动生成 `feature-日期-编号` | `feature-20260516-001` |
| 字符串（如 `"feat/login"`） | 使用指定名称，重复则追加序号 | `feat/login` → `feat/login-001` |
| `false` | 不创建新分支，保持当前分支 | — |

### 自动生成逻辑（伪代码）

```python
def create_task_branch(dir_path, branch_config):
    """根据配置创建任务分支"""
    if branch_config is False:
        return  # 不创建分支

    today = datetime.now().strftime("%Y%m%d")

    if branch_config is True or branch_config is None:
        # 自动生成: feature-YYYYMMDD-NNN
        prefix = f"feature-{today}"
        branch_name = find_next_available_branch(dir_path, prefix)
    else:
        # 用户指定名称，重复则追加序号
        if branch_exists(dir_path, branch_config):
            branch_name = find_next_available_branch(dir_path, branch_config)
        else:
            branch_name = branch_config

    subprocess.run(["git", "checkout", "-b", branch_name], cwd=dir_path)

def find_next_available_branch(dir_path, prefix):
    """找到下一个可用的分支编号"""
    for i in range(1, 1000):
        name = f"{prefix}-{i:03d}"
        if not branch_exists(dir_path, name):
            return name
    raise Exception("分支编号超出范围")

def branch_exists(dir_path, name):
    result = subprocess.run(
        ["git", "branch", "--list", name],
        cwd=dir_path, capture_output=True, text=True
    )
    return result.stdout.strip() != ""
```

### 可行性评估

| 项目 | 评估 | 说明 |
|------|------|------|
| 自动生成分支名 | ✅ 简单 | `git branch --list` 查询已有分支，纯 Python 逻辑 |
| 用户指定分支名 | ✅ 简单 | 同上 |
| 重复检测与序号追加 | ✅ 简单 | 遍历 `-001` 到 `-999` 找第一个可用的 |
| `branch: false` 跳过 | ✅ 简单 | 条件判断即可 |

---

## 完整执行流程

```
读取 tasks.yaml
    ↓
遍历每个任务:
    ↓
    ① git status 检查目标目录
    ↓ (dirty)
    ② 调用 Claude 提交暂存区改动
    ↓
    ③ 调用 Claude 提交工作区改动
    ↓
    ④ git status 确认干净
    ↓
    ⑤ 根据 branch 配置创建新分支
    ↓
    ⑥ 调用 Claude 执行任务 prompt
    ↓
    ⑦ 记录状态，继续下一个任务
```

## 风险与应对

| 风险 | 应对 |
|------|------|
| 自动提交了不想要的代码 | prompt 中提示检查敏感文件；可在 tasks.yaml 增加 `auto_commit: false` 跳过自动提交 |
| 分支创建失败（如 detached HEAD） | 捕获异常，标记任务失败并记录日志 |
| Claude 生成的 commit message 不准确 | 可接受——这是临时提交保护，目的是保存当前状态，不是最终 commit |
| 目标目录不是 Git 仓库 | 检测并跳过 git 相关步骤，直接执行任务 |

## 后续可选增强

- `auto_commit: false` — 跳过自动提交，直接在脏工作区执行（用户自行承担风险）
- `base_branch` — 指定从哪个分支创建新分支（默认从当前分支）
- 任务执行完后自动 commit 任务产出（复用同样的 commit prompt）

# Git 工作流（双远端策略）

> 目标：**GitHub 全量、Gitee 精简、互不污染**。
> 远端：`github`（GitHub，私有，全量）· `origin`（Gitee，对外/CI，精简）。

## 分支职责

| 分支 | 内容 | 允许推送到 |
|---|---|---|
| `main` | 稳定可发布代码 | `github` + `origin` |
| `develop` | 集成分支（代码 + 计划文档） | `github` + `origin` |
| `feat/*` `fix/*` … | 功能/修复（从 `develop` 切出） | 按需（一般 `github`） |
| **`private-docs`** | **私有资料**：`docs/` + `面试准备/` | **仅 `github`** |

> `develop` / `main` 永远**不包含** `docs/` 与 `面试准备/`，两个远端内容一致；私有资料只存在于 `private-docs`。

## 代码：正常推两个远端

```bash
git push github develop && git push origin develop
# 发布时再走 PR： develop → main
```

## 私有资料：用独立 worktree 维护（推荐）

> 原因：`docs/` 在 `develop` 被 `.gitignore` 忽略、在 `private-docs` 被跟踪，
> 同一目录来回切分支会冲突或丢文件。用 `git worktree` 建独立目录最稳。

```bash
# 一次性创建（本机已创建于 ../copilot-lite-private）
git worktree add ../copilot-lite-private private-docs

# 每次更新私有资料
cd ../copilot-lite-private
git add -f docs 面试准备            # docs/ 被忽略，需 -f
git commit -m "docs: 更新私有资料"
git push github private-docs       # 只推 GitHub

# 用完可移除工作区（分支仍在）
git worktree remove ../copilot-lite-private
```

## 防误推守卫（推荐安装）

`scripts/git-hooks/pre-push` 会**拒绝把 `private-docs` 推到非 GitHub 远端**：

```bash
cp scripts/git-hooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

## 约定与注意

- `AGENTS.md`（含本机路径）与 `backend/.env`（密钥）在任何分支都不入库；保持在 `.gitignore`。
- `docs/` 被忽略；在 `private-docs` 中新增文件需要 `git add -f`。
- 新功能仍遵循「一功能一分支 + 防回归测试 + 全绿 → 经批准后合并」。
- **不要把 `private-docs` 合并回 `develop` / `main`**（会污染精简远端）。

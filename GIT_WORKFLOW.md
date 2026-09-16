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

## 防误推守卫（**必须安装**）

`scripts/git-hooks/pre-push` 会**拒绝把 `private-docs` 推到非 GitHub 远端**：

```bash
cp scripts/git-hooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

### 踩过的坑：**不要用 `core.hooksPath`，除非用绝对路径**

本仓曾设置 `git config core.hooksPath scripts/git-hooks`（相对路径）。Git 把相对 `hooksPath`
**按工作树根目录**解析，于是：主工作树正常（`scripts/git-hooks/` 存在），但
`git worktree add ../copilot-lite-private private-docs` 建出的私有工作树里该目录不存在
→ Git **静默跳过全部钩子**（不报错、不告警），**防误推守卫在最需要它的那个工作树里恰好失效**。
实测：在私有工作树 `git push --dry-run origin private-docs` 会直接放行到 Gitee。

因此：

- **不设 `core.hooksPath`**（回退到共用的 `.git/hooks/`，工作树之间自动共享，见下）；
- 若确实要用 `core.hooksPath`，**必须写绝对路径**（如
  `git config core.hooksPath /path/to/copilot-lite/.git/hooks`），或**每个工作树都放一份**
  `scripts/git-hooks/pre-push`；
- **自检命令**（换机器/新建工作树后必跑，预期被拒绝且退出码非 0）：

  ```bash
  cd ../copilot-lite-private
  git push --dry-run origin private-docs   # 应输出 [pre-push] 拒绝：…
  echo $?                                  # 非 0
  git ls-remote --heads origin private-docs  # 应为空（未泄露）
  ```

> 为什么 `git init` 后的 `.git/hooks/` 能被多个工作树共享：`.git/hooks/` 属**公共目录**
> （`git rev-parse --git-common-dir`），`git worktree add` 出来的工作树共用它；而 `hooksPath`
> 是配置层面的重定向，会把这份共享**覆盖成各工作树自己的相对路径**。

## 约定与注意

- `AGENTS.md`（含本机路径）与 `backend/.env`（密钥）在任何分支都不入库；保持在 `.gitignore`。
- `docs/` 被忽略；在 `private-docs` 中新增文件需要 `git add -f`。
- 新功能仍遵循「一功能一分支 + 防回归测试 + 全绿 → 经批准后合并」。
- **不要把 `private-docs` 合并回 `develop` / `main`**（会污染精简远端）。

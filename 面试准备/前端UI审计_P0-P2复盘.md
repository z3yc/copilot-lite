# 前端 UI 审计与改进 · P0-P2 复盘（面试话术）

> 私有复盘，仅 GitHub `private-docs` 分支。对应公开工程记录：`web/UI_AUDIT_AND_PLAN.md`、`web/.interface-design/system.md`。

## 面试话术（一句话）

我接手时前端是"功能堆叠、体验硌手"：零设计令牌导致暗色模式选中态对比度只有 1.11:1、图标按钮无 aria-label、导航 div 无法键盘操作、全站无响应式。我没有零散打补丁，而是先建 primitive→semantic 令牌层、抽出 AppShell / AsyncBoundary / IconButton 等 8 个基础组件，再用 design-auditor 的 19 类模型量化前后分，P0 把可访问性与对比度一次性拉到 WCAG AA。工程上保持每次提交只解决一个问题，全部补 vitest。

## 可展开的技术点

1. **令牌分层**：primitive（`--indigo-600`）→ semantic（`--accent-strong`）；组件只准用 semantic，暗色只换 semantic 值，根因消除"硬编码浅色底"。
2. **对比度可量化、可回归**：把 WCAG 亮度算法写进 vitest，直接断言令牌配对 ≥4.5/≥3，改色即跑测试，不靠肉眼。
3. **回归护栏**：断言 `styles.css` 不再出现裸 `#4f6ef7/#eef1ff`、不再出现 `transition: all`、必须存在 `prefers-reduced-motion` 块。
4. **根因优先于症状**：19 类里 40+ 问题收敛为 4 个根因（无令牌/无响应式/零 ARIA/暗色硬编码），一次性回收大部分分值。
5. **可访问性基座**：图标按钮统一 aria-label + 40px hit area；导航从 div/li 改语义元素 + focus-visible + aria-current。

## 踩坑

- （实施后补）例如：Ant Design 的 `size="small"` 图标按钮默认 24px，需要伪元素扩展而不是直接改 size，否则布局跳动。
- （实施后补）暗色 `--text-muted` 不能沿用浅色的 `#646b7d`（暗底仅 3.45），必须 `#8c8c8c`——说明"某颜色达标"必须绑定具体背景。

## 基线数据（审计前）

- Overall 0/100（公式触底，5🚫/8🔴/22🟡/7🟢）；Accessibility 0/100；Ethics 100；Usability 88。
- 证据：全站 `aria-*`=0、`role=`=0、`@media`=0、`prefers-reduced-motion`=0。
- 关键对比度：暗色选中态 1.11:1；`--dim` 2.95–3.19；品牌蓝 4.29。

## 改进后（待填）

- 重跑 design-auditor：Overall __/100；Accessibility __/100。
- git 提交：`feat/web-ui-polish` 分支，逐问题一个 commit。

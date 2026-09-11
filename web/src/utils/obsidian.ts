import { renderMarkdown } from "./markdown";

/** 标题归一化：与后端 slugify 保持一致（双链匹配用）。 */
function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/[^0-9a-z\-\u4e00-\u9fff]/g, "")
    .replace(/^-+|-+$/g, "");
}

/**
 * 渲染 Obsidian 文本（仅供展示，不改原文）：
 * - 去掉模板占位 `{{...}}`（模板未渲染时的字面量，展示无意义）；
 * - `[[目标]]` / `[[目标|别名]]` / `![[目标]]` → 内部锚点 `#wiki-<slug>`；
 * - 最后走统一消毒渲染（唯一安全入口）。
 */
export function renderObsidian(text: string): string {
  if (!text) return "";
  const withoutTemplates = text.replace(/\{\{[^}]*\}\}/g, "");
  const withLinks = withoutTemplates.replace(
    /!?\[\[([^\[\]|#]+?)(?:#[^\[\]|]+?)?(?:\|([^\]]+?))?\]\]/g,
    (_match, target: string, alias?: string) => {
      const label = (alias || target).trim();
      const slug = slugify(target.trim());
      return `[${label}](#wiki-${encodeURIComponent(slug)})`;
    }
  );
  return renderMarkdown(withLinks);
}

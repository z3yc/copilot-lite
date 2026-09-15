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

/** 可被 Obsidian 双链显式带上的文档扩展名（归一化时剥离）。 */
const DOC_EXTS = [".markdown", ".md", ".txt", ".pdf", ".docx", ".doc"];

/**
 * 按 Obsidian 解析规则归一化双链目标为页面 slug（与后端 `normalize_link_target` 一致）：
 * 支持子目录路径 `folder/Note`、显式扩展名 `Note.md`、块引用 `Note^block`；
 * 最终按文件名（去扩展名）匹配页面 slug。
 */
export function normalizeWikiTarget(target: string): string {
  let text = (target || "").trim();
  text = text.split("#", 1)[0].split("^", 1)[0].trim();
  text = text.replace(/\\/g, "/").split("/").pop()?.trim() ?? "";
  const low = text.toLowerCase();
  const ext = DOC_EXTS.find((e) => low.endsWith(e));
  if (ext) text = text.slice(0, text.length - ext.length);
  return slugify(text);
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
      const slug = normalizeWikiTarget(target);
      return `[${label}](#wiki-${encodeURIComponent(slug)})`;
    }
  );
  return renderMarkdown(withLinks);
}

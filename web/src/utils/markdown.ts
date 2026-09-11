import { marked } from "marked";
import DOMPurify from "dompurify";

/**
 * 渲染 Markdown 并消毒——LLM 输出与 Wiki 正文的唯一安全入口。
 * `dangerouslySetInnerHTML` 只允许使用本函数的返回值（AGENTS.md §5）。
 */
export function renderMarkdown(text: string): string {
  try {
    const html = marked.parse(text, { async: false }) as string;
    return DOMPurify.sanitize(html);
  } catch {
    return text;
  }
}

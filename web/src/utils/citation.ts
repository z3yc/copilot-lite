/** 引用跳转目标解析：点这条引用去哪（App 与 ChatPanel 共用同一判据）。 */

import type { Citation } from "../types";

export type CitationTarget =
  | { kind: "wiki"; pageId: string; spaceId?: string }
  | { kind: "doc"; docId: string };

/**
 * 解析引用的跳转目标；不可跳转时返回 null。
 *
 * `source_kind === "wiki"` 时不降级为文档跳转：没有 `page_id` 只说明页面已删除
 * 或无法解析，此时宁可不跳——旧行为会把用户带到知识库里另一份文档（看着像跳了，
 * 其实没到目标）。旧格式（无 `source_kind`）仍按 `document_id` 尽力跳转。
 */
export function resolveCitationTarget(c: Citation): CitationTarget | null {
  if (c.source_kind === "wiki") {
    if (!c.wiki?.page_id) return null;
    return { kind: "wiki", pageId: c.wiki.page_id, spaceId: c.wiki.space_id || undefined };
  }
  if (c.document_id) return { kind: "doc", docId: c.document_id };
  return null;
}

/** 正文内引用链接的 href 前缀（前端拦截后转成跳转/提示，不做页面锚点导航）。 */
export const CITE_HREF_PREFIX = "#cite-";

/** 正文 `[n]` 的正则：后面紧跟 `(` 的是已有的 Markdown 链接，不处理。 */
const BRACKET_REF = /\[(\d{1,3})\](?!\()/g;

function linkifySegment(segment: string, valid: Set<number>): string {
  // 行内代码不处理（避免在代码内容里插入链接）；split 带捕获组 → 奇数下标是代码片段
  return segment
    .split(/(`[^`\n]*`)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(BRACKET_REF, (m, n) =>
            valid.has(Number(n)) ? `[[${n}]](${CITE_HREF_PREFIX}${n})` : m
          )
    )
    .join("");
}

/**
 * 把回答正文里的 `[n]` 转成可点的 Markdown 链接（`[[n]](#cite-n)`，保留方括号外观）。
 *
 * 背景：模型会把引用写成正文的一部分（`每周清空一次 [1]`，甚至末尾自写一份「来源：」
 * 清单）——这些 `[n]` 原本是纯文本，点不了；来源行那排 `[n]` 才是可点的。
 * 仅当存在对应引用时才转（无对应引用保持纯文本，不做死链）。
 * 行内代码与围栏代码块内不转（否则会往代码里插链接）。
 */
export function linkifyCitations(markdown: string, indexes: Iterable<number>): string {
  const valid = new Set(indexes);
  if (valid.size === 0) return markdown;
  // 围栏代码块整体跳过：split 带捕获组 → 奇数下标是代码块
  return markdown
    .split(/(```[\s\S]*?(?:```|$))/g)
    .map((segment, i) => (i % 2 === 1 ? segment : linkifySegment(segment, valid)))
    .join("");
}

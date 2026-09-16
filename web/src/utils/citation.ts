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

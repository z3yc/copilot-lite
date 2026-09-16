/**
 * 引用跳转目标解析：决定「点这条引用去哪」。
 *
 * 关键约束（防回归）：`source_kind === "wiki"` 时**绝不降级为文档跳转**——
 * 没有 page_id 只说明页面已删除/不可解析，此时宁可不跳，也不能把用户带到
 * 知识库里的另一份文档（旧行为：看着像跳了，其实没到目标）。
 */

import { describe, expect, it } from "vitest";

import type { Citation } from "../types";
import { linkifyCitations, resolveCitationTarget } from "./citation";

function cite(overrides: Partial<Citation>): Citation {
  return { index: 1, chunk_id: "c1", source: "来源", ...overrides };
}

describe("resolveCitationTarget", () => {
  it("Wiki 引用解析到页面（带空间）", () => {
    const target = resolveCitationTarget(
      cite({
        source_kind: "wiki",
        document_id: "d1",
        wiki: { page_id: "p1", space_id: "s1", space_name: "空间", rel_path: "a.md" },
      })
    );
    expect(target).toEqual({ kind: "wiki", pageId: "p1", spaceId: "s1" });
  });

  it("Wiki 引用缺失 page_id 时不跳转（不回退到文档）", () => {
    expect(
      resolveCitationTarget(cite({ source_kind: "wiki", document_id: "d1" }))
    ).toBeNull();
  });

  it("文档引用解析到文档（含旧格式：无 source_kind 但有 document_id）", () => {
    expect(resolveCitationTarget(cite({ source_kind: "document", document_id: "d9" }))).toEqual({
      kind: "doc",
      docId: "d9",
    });
    expect(resolveCitationTarget(cite({ document_id: "d9" }))).toEqual({
      kind: "doc",
      docId: "d9",
    });
  });

  it("无任何目标时返回 null", () => {
    expect(resolveCitationTarget(cite({}))).toBeNull();
    expect(resolveCitationTarget(cite({ source_kind: "document" }))).toBeNull();
  });

  it("wiki 但没有 space_id 时仍可跳转（只有 page_id 是必需项）", () => {
    const target = resolveCitationTarget(
      cite({
        source_kind: "wiki",
        wiki: { page_id: "p1", space_id: "", space_name: "空间", rel_path: "a.md" },
      })
    );
    expect(target).toEqual({ kind: "wiki", pageId: "p1", spaceId: undefined });
  });
});

describe("linkifyCitations", () => {
  it("存在对应引用时把 [n] 转成可点链接（保留方括号外观）", () => {
    expect(linkifyCitations("见 [1] 与 [9]", [1])).toBe("见 [[1]](#cite-1) 与 [9]");
  });

  it("无对应引用的编号保持纯文本（不做死链）", () => {
    expect(linkifyCitations("见 [7]", [1, 2])).toBe("见 [7]");
  });

  it("不动行内代码与围栏代码块内的 [n]", () => {
    const md = "行内 `[1]` 与\n\n```python\nprint('[1]')\n```\n\n正文 [1]";
    const out = linkifyCitations(md, [1]);
    expect(out).toContain("行内 `[1]`");
    expect(out).toContain("print('[1]')");
    expect(out.endsWith("正文 [[1]](#cite-1)")).toBe(true);
  });

  it("不破坏已有的 Markdown 链接", () => {
    expect(linkifyCitations("[1](https://x.test)", [1])).toBe("[1](https://x.test)");
  });

  it("无引用时不改写正文", () => {
    expect(linkifyCitations("见 [1]", [])).toBe("见 [1]");
  });
});

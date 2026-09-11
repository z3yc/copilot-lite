import { describe, expect, it } from "vitest";

import { renderObsidian } from "./obsidian";

describe("renderObsidian", () => {
  it("去除模板占位 {{...}}", () => {
    const html = renderObsidian("{{date}}\n{{title}}\n正文内容");
    expect(html).not.toContain("{{");
    expect(html).toContain("正文内容");
  });

  it("双链转为内部锚点（含别名）", () => {
    const html = renderObsidian("见 [[Note B|别名]] 与 ![[Img]]");
    expect(html).toContain('href="#wiki-note-b"');
    expect(html).toContain("别名");
    expect(html).toContain('href="#wiki-img"');
  });
});

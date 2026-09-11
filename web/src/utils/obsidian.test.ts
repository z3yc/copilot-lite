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

  it("双链带子目录/扩展名/块引用时锚点归一化为文件名 slug", () => {
    const html = renderObsidian(
      "[[sub/Note B]] [[Note B.md]] [[Note B^block-id]] [[Other/Deep/Note B]]"
    );
    expect(html.match(/href="#wiki-note-b"/g)).toHaveLength(4);
  });
});

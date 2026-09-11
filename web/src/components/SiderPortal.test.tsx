/**
 * SiderPortal：导航目录渲染进「工作区」侧栏的挂载契约。
 * - 无 Provider（单测/独立使用）→ 行内渲染
 * - App 上下文（enabled）→ portal 到挂载点；挂载点未就绪时不渲染
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiderNavContext } from "../contexts/SiderNav";
import SiderPortal from "./SiderPortal";

describe("SiderPortal", () => {
  it("无 Provider 时行内渲染（保证可测试/可复用）", () => {
    render(
      <SiderPortal>
        <span>导航内容</span>
      </SiderPortal>
    );
    expect(screen.getByText("导航内容")).toBeInTheDocument();
  });

  it("上下文就绪时 portal 到侧栏挂载点", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    render(
      <SiderNavContext.Provider value={{ el: host, enabled: true }}>
        <SiderPortal>
          <span>导航内容</span>
        </SiderPortal>
      </SiderNavContext.Provider>
    );
    expect(host.textContent).toContain("导航内容");
    host.remove();
  });

  it("上下文启用但挂载点未就绪时不渲染（避免闪动）", () => {
    const { container } = render(
      <SiderNavContext.Provider value={{ el: null, enabled: true }}>
        <SiderPortal>
          <span>导航内容</span>
        </SiderPortal>
      </SiderNavContext.Provider>
    );
    expect(container.textContent).toBe("");
  });
});

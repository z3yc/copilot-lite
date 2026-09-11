/** ErrorBoundary 测试：正常渲染子节点 / 子节点抛错时展示兜底 UI。 */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "./ErrorBoundary";

function Bomb(): JSX.Element {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // React 会预期性打印组件堆栈，测试中静音避免噪音
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("正常渲染子节点", () => {
    render(
      <ErrorBoundary>
        <div>正常内容</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("正常内容")).toBeInTheDocument();
  });

  it("子节点抛错时展示兜底并提供刷新按钮", () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );
    expect(screen.getByText("页面出现异常")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /刷新页面/ })).toBeInTheDocument();
  });
});

/** vitest 全局测试环境准备：jest-dom 匹配器 + jsdom 缺失的浏览器 API mock。 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// antd 等组件依赖 matchMedia（响应式断点），jsdom 未实现 → 全局 mock
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// 部分 antd 组件（Modal/Drawer 等）依赖 ResizeObserver
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverMock);

// jsdom 未实现 Element.scrollTo（ChatPanel 滚动到底部用）
Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo;

// jsdom 未实现 URL.createObjectURL / revokeObjectURL（会话导出下载用）
if (!URL.createObjectURL) {
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
}

// react-force-graph-2d 依赖 canvas 渲染，jsdom 无法绘制；测试中替换为可点击节点列表。
vi.mock("react-force-graph-2d", async () => {
  const { createElement } = await import("react");
  interface MockNode {
    id?: string | number;
    title?: string;
  }
  interface MockProps {
    graphData?: { nodes?: MockNode[] };
    onNodeClick?: (node: MockNode) => void;
  }
  return {
    default: ({ graphData, onNodeClick }: MockProps) =>
      createElement(
        "div",
        { "data-testid": "force-graph" },
        (graphData?.nodes ?? []).map((node) =>
          createElement(
            "button",
            { key: String(node.id), onClick: () => onNodeClick?.(node) },
            node.title
          )
        )
      ),
  };
});

// 每个测试后自动清理 DOM 与 localStorage（RTL v16 在非 globals 模式下需手动 cleanup）
afterEach(() => {
  cleanup();
  localStorage.clear();
});

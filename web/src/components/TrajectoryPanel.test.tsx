/** TrajectoryPanel 冒烟测试：空轨迹不渲染；展开后可见路由/节点/工具/耗时。 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Trajectory } from "../types";
import TrajectoryPanel from "./TrajectoryPanel";

const trajectory: Trajectory = {
  engine: "langgraph",
  total_ms: 120,
  truncated: false,
  steps: [
    { type: "route", route: "kb", source: "llm", ms: 40 },
    { type: "node", node: "kb_agent" },
    {
      type: "tool",
      name: "kb_search",
      arguments: '{"query":"x"}',
      result: "片段",
      status: "ok",
      ms: 12,
    },
    { type: "answer", chars: 6 },
  ],
};

describe("TrajectoryPanel", () => {
  it("无轨迹时不渲染", () => {
    const { container } = render(<TrajectoryPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("steps 为空时不渲染", () => {
    const { container } = render(
      <TrajectoryPanel trajectory={{ ...trajectory, steps: [] }} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("展开后展示引擎/步数/总耗时与各步内容", () => {
    render(<TrajectoryPanel trajectory={trajectory} />);
    const header = screen.getByText(/本次回答轨迹/);
    expect(header).toBeInTheDocument();
    expect(screen.getByText(/4 步/)).toBeInTheDocument();
    expect(screen.getByText(/120ms/)).toBeInTheDocument();

    fireEvent.click(header);

    expect(screen.getByText("kb_agent")).toBeInTheDocument();
    expect(screen.getByText("kb_search")).toBeInTheDocument();
    expect(screen.getByText(/40ms/)).toBeInTheDocument();
    // 精确断言：source="llm" 必须映射为「模型判定」，防止两分支被写反仍全绿
    expect(screen.getByText(/模型判定/)).toBeInTheDocument();
  });

  it("截断时标注「已截断」", () => {
    render(<TrajectoryPanel trajectory={{ ...trajectory, truncated: true }} />);
    expect(screen.getByText(/已截断/)).toBeInTheDocument();
  });

  it("待确认的工具步标注未执行", () => {
    render(
      <TrajectoryPanel
        trajectory={{
          ...trajectory,
          steps: [
            { type: "tool", name: "todo_create", arguments: "{}", status: "pending_confirmation" },
          ],
        }}
      />
    );
    fireEvent.click(screen.getByText(/本次回答轨迹/));
    expect(screen.getByText(/待确认/)).toBeInTheDocument();
  });

  it("外部数据按文本渲染，不产生 HTML 元素（AGENTS §5 红线）", () => {
    render(
      <TrajectoryPanel
        trajectory={{
          ...trajectory,
          steps: [
            {
              type: "tool",
              name: "kb_search",
              arguments: '{"query": "<b>粗体</b>"}',
              result: "<img src=x onerror=alert(1)>",
              status: "ok",
              ms: 5,
            },
          ],
        }}
      />
    );
    fireEvent.click(screen.getByText(/本次回答轨迹/));

    // 载荷以文本形式可见（说明未被当作 HTML 解析）
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    // 且没有真的生成该元素
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
  });
});

/**
 * WikiGraph 组件测试：节点渲染/点击跳转、截断提示、标签过滤。
 * 全部 mock api（react-force-graph-2d 已在 test/setup.ts 全局替换为可点击列表）。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import WikiGraphView from "./WikiGraph";

vi.mock("../api", () => ({ fetchWikiGraph: vi.fn() }));

const mocked = vi.mocked(api);

const GRAPH = {
  nodes: [
    {
      id: "p1",
      title: "A",
      slug: "a",
      space_id: "s1",
      space: "vault",
      degree: 2,
      tags: ["alpha", "beta"],
    },
    {
      id: "p2",
      title: "B",
      slug: "b",
      space_id: "s1",
      space: "vault",
      degree: 1,
      tags: ["beta"],
    },
  ],
  edges: [{ source: "p1", target: "p2", kind: "link", relation: null }],
  total_nodes: 2,
  truncated: false,
};

describe("WikiGraphView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchWikiGraph.mockResolvedValue(GRAPH);
  });

  it("渲染节点并在点击时打开对应页面", async () => {
    const onOpenPage = vi.fn();
    render(<WikiGraphView spaceId="s1" spaceName="vault" onOpenPage={onOpenPage} />);

    expect(await screen.findByTestId("force-graph")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "A" }));
    expect(onOpenPage).toHaveBeenCalledWith("p1");
  });

  it("节点超限时显示截断提示", async () => {
    mocked.fetchWikiGraph.mockResolvedValue({
      ...GRAPH,
      total_nodes: 500,
      truncated: true,
    });
    render(<WikiGraphView spaceId="s1" onOpenPage={vi.fn()} />);

    expect(
      await screen.findByText(/仅展示关联度最高的 2 \/ 500 个节点/)
    ).toBeInTheDocument();
  });

  it("选择标签后携带 tag 参数重新拉取", async () => {
    render(<WikiGraphView spaceId="s1" onOpenPage={vi.fn()} />);
    await screen.findByTestId("force-graph");

    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByText("#alpha"));

    await waitFor(() =>
      expect(mocked.fetchWikiGraph).toHaveBeenCalledWith("s1", "alpha")
    );
  });

  it("未选空间时不请求且显示空态", () => {
    render(<WikiGraphView onOpenPage={vi.fn()} />);
    expect(mocked.fetchWikiGraph).not.toHaveBeenCalled();
    expect(screen.getByText(/请先导入 vault/)).toBeInTheDocument();
  });
});

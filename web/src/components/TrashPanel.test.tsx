/** TrashPanel 测试：空状态、列表渲染、恢复调用（mock api）。 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import type { TrashItem } from "../types";
import TrashPanel from "./TrashPanel";

vi.mock("../api", () => ({
  fetchTrash: vi.fn(),
  restoreTrashItem: vi.fn(),
}));

const mocked = vi.mocked(api);

const ITEMS: TrashItem[] = [
  { type: "todo", id: "t1", label: "买菜", deleted_at: "2026-09-11T10:00:00" },
  { type: "document", id: "d1", label: "笔记.md", deleted_at: null },
];

describe("TrashPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("空回收站展示空状态", async () => {
    mocked.fetchTrash.mockResolvedValue([]);
    render(<TrashPanel />);
    expect(await screen.findByText("回收站为空")).toBeInTheDocument();
  });

  it("展示已删除数据", async () => {
    mocked.fetchTrash.mockResolvedValue(ITEMS);
    render(<TrashPanel />);
    expect(await screen.findByText("买菜")).toBeInTheDocument();
    expect(screen.getByText("笔记.md")).toBeInTheDocument();
  });

  it("点击恢复调用接口", async () => {
    mocked.fetchTrash.mockResolvedValue(ITEMS);
    mocked.restoreTrashItem.mockResolvedValue({ restored: "t1", type: "todo" });
    render(<TrashPanel />);
    await screen.findByText("买菜");
    fireEvent.click(screen.getAllByRole("button", { name: /恢复/ })[0]);
    await waitFor(() =>
      expect(mocked.restoreTrashItem).toHaveBeenCalledWith("todo", "t1")
    );
  });
});

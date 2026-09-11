/**
 * KbPanel 组件测试：列表/错误态，以及“删除后按当前分类重载”的防回归用例。
 * 全部 mock api 模块，不触发真实网络。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import type { DocItem } from "../types";
import KbPanel from "./KbPanel";

vi.mock("../api", () => ({
  fetchDocs: vi.fn(),
  fetchDocDetail: vi.fn(),
  deleteDoc: vi.fn(),
  retryDoc: vi.fn(),
  uploadDocs: vi.fn(),
}));

const mocked = vi.mocked(api);

const DOCS: DocItem[] = [
  { id: "d1", title: "PDF A", source_type: "pdf", status: "ready", chunk_count: 1 },
  { id: "d2", title: "笔记 B", source_type: "md", status: "ready", chunk_count: 2 },
];

function renderPanel() {
  return render(<KbPanel activeCat="pdf" onCatChange={vi.fn()} />);
}

describe("KbPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchDocs.mockResolvedValue(DOCS);
  });

  it("加载失败时展示错误态与重试（而非空态）", async () => {
    mocked.fetchDocs.mockRejectedValueOnce(new Error("服务不可用"));
    renderPanel();
    expect(await screen.findByText("加载知识库失败")).toBeInTheDocument();
    expect(screen.getByText("服务不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重\s*试/ })).toBeInTheDocument();
  });

  it("删除文档后按当前分类重新加载（回归：不丢失 activeCat 筛选）", async () => {
    mocked.deleteDoc.mockResolvedValue({ deleted: "d1" });
    renderPanel();
    await screen.findByText("PDF A");

    // 点击第一张卡片上的删除图标，确认后触发删除
    const deleteIcon = screen.getAllByRole("img", { name: "delete" })[0];
    fireEvent.click(deleteIcon.closest("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("button", { name: "OK" }));

    await waitFor(() => expect(mocked.deleteDoc).toHaveBeenCalledWith("d1"));
    await waitFor(() =>
      expect(mocked.fetchDocs).toHaveBeenLastCalledWith(undefined, "pdf")
    );
  });
});

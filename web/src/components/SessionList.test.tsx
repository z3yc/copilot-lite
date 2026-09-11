/**
 * SessionList 组件测试：列表渲染、搜索防抖、重命名、导出、删除。
 * 全部 mock api 模块，不触发真实网络。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import type { Session } from "../types";
import SessionList from "./SessionList";

vi.mock("../api", () => ({
  fetchSessions: vi.fn(),
  deleteSession: vi.fn(),
  renameSession: vi.fn(),
  exportSessionMarkdown: vi.fn(),
}));

const mocked = vi.mocked(api);

const SESSIONS: Session[] = [
  { id: "s1", title: "面试准备", message_count: 3 },
  { id: "s2", title: "随手记", message_count: 1 },
];

function renderList(overrides?: Partial<React.ComponentProps<typeof SessionList>>) {
  const props = {
    activeId: null,
    onSelect: vi.fn(),
    onNew: vi.fn(),
    ...overrides,
  };
  return render(<SessionList {...props} />);
}

describe("SessionList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchSessions.mockResolvedValue(SESSIONS);
  });

  it("渲染会话列表与消息数", async () => {
    renderList();
    expect(await screen.findByText("面试准备")).toBeInTheDocument();
    expect(screen.getByText("随手记")).toBeInTheDocument();
    expect(screen.getByText(/3 条消息/)).toBeInTheDocument();
  });

  it("搜索关键词经防抖后传给后端", async () => {
    renderList();
    await screen.findByText("面试准备");
    fireEvent.change(screen.getByPlaceholderText("搜索会话标题"), {
      target: { value: "面试" },
    });
    await waitFor(() =>
      expect(mocked.fetchSessions).toHaveBeenLastCalledWith("面试")
    );
  });

  it("重命名调用接口并更新显示", async () => {
    mocked.renameSession.mockResolvedValue({
      id: "s1",
      title: "新标题",
      message_count: 3,
    });
    renderList();
    await screen.findByText("面试准备");

    fireEvent.click(screen.getAllByTitle("重命名")[0]);
    const input = screen.getByDisplayValue("面试准备");
    fireEvent.change(input, { target: { value: "新标题" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(mocked.renameSession).toHaveBeenCalledWith("s1", "新标题")
    );
    expect(await screen.findByText("新标题")).toBeInTheDocument();
  });

  it("导出调用 Markdown 接口", async () => {
    mocked.exportSessionMarkdown.mockResolvedValue("# 面试准备");
    renderList();
    await screen.findByText("面试准备");
    fireEvent.click(screen.getAllByTitle("导出 Markdown")[0]);
    await waitFor(() =>
      expect(mocked.exportSessionMarkdown).toHaveBeenCalledWith("s1")
    );
  });

  it("点击会话触发 onSelect", async () => {
    const onSelect = vi.fn();
    renderList({ onSelect });
    fireEvent.click(await screen.findByText("面试准备"));
    expect(onSelect).toHaveBeenCalledWith("s1");
  });

  it("加载失败时展示错误态与重试入口（而非误导性空态）", async () => {
    mocked.fetchSessions.mockRejectedValueOnce(new Error("网络错误"));
    renderList();
    expect(await screen.findByText("加载会话失败")).toBeInTheDocument();
    expect(screen.getByText("网络错误")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重\s*试/ })).toBeInTheDocument();
    expect(screen.queryByText("暂无会话")).not.toBeInTheDocument();
  });
});

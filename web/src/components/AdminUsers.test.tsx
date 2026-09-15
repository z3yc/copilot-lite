/**
 * AdminUsers 测试：列表渲染、新建、软删二次确认、恢复。全部 mock api，不触网。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import AdminUsers from "./AdminUsers";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchAdminUsers: vi.fn(),
    createAdminUser: vi.fn(),
    updateAdminUser: vi.fn(),
    deleteAdminUser: vi.fn(),
    restoreAdminUser: vi.fn(),
    forceLogoutAdminUser: vi.fn(),
  };
});

const mocked = vi.mocked(api);

const USERS = [
  {
    id: "1",
    username: "alice",
    role: "admin",
    status: "active",
    has_key: true,
    created_at: "2026-01-01T00:00:00",
  },
  {
    id: "2",
    username: "bob",
    role: "user",
    status: "disabled",
    has_key: false,
    created_at: "2026-01-02T00:00:00",
    deleted_at: "2026-01-03T00:00:00",
  },
];

/** 按可见文本找按钮（去除 antd 两字按钮自动插入的空格，忽略图标节点）。 */
function clickButtonByText(text: string, index = 0) {
  const target = text.replace(/\s/g, "");
  const buttons = screen
    .getAllByRole("button")
    .filter((b) => (b.textContent ?? "").replace(/\s/g, "") === target);
  fireEvent.click(buttons[index]);
}

describe("AdminUsers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchAdminUsers.mockResolvedValue({
      items: USERS,
      total: USERS.length,
      page: 1,
      page_size: 20,
    });
    mocked.createAdminUser.mockResolvedValue({ ...USERS[1] });
    mocked.deleteAdminUser.mockResolvedValue({ deleted: "1", soft: true });
    mocked.restoreAdminUser.mockResolvedValue({ id: "2", soft: true, message: "已恢复" });
    mocked.updateAdminUser.mockResolvedValue({
      ...USERS[0],
      session_count: 0,
      document_count: 0,
    });
  });

  it("渲染用户列表与状态标签", async () => {
    render(<AdminUsers />);
    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("已删除")).toBeInTheDocument();
    expect(screen.getByText("已禁用")).toBeInTheDocument();
  });

  it("新建用户提交调用 createAdminUser", async () => {
    render(<AdminUsers />);
    await screen.findByText("alice");

    clickButtonByText("新建用户");
    fireEvent.change(await screen.findByPlaceholderText("如 alice"), {
      target: { value: "carol" },
    });
    fireEvent.change(screen.getByPlaceholderText("至少 6 位"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /OK|确定/ }));

    await waitFor(() =>
      expect(mocked.createAdminUser).toHaveBeenCalledWith({
        username: "carol",
        password: "secret123",
        role: "user",
      })
    );
  });

  it("软删除需二次确认并带原因", async () => {
    render(<AdminUsers />);
    await screen.findByText("alice");

    clickButtonByText("删除");
    expect(await screen.findByText("删除用户（软删除）")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/删除原因/), {
      target: { value: "违规" },
    });
    clickButtonByText("确认删除");

    await waitFor(() =>
      expect(mocked.deleteAdminUser).toHaveBeenCalledWith("1", "违规")
    );
  });

  it("恢复已删除用户调用 restoreAdminUser", async () => {
    render(<AdminUsers />);
    await screen.findByText("bob");
    clickButtonByText("恢复");
    await waitFor(() => expect(mocked.restoreAdminUser).toHaveBeenCalledWith("2"));
  });
});

/**
 * App 集成回归：管理后台/个人主页覆盖视图与「工作区」侧栏目录的关系。
 *
 * 修复点（UX：全局导航与上下文目录分离）：
 * - 覆盖视图打开时不再渲染工作区目录区（避免空白列表 / 点了没反应的假控件）；
 * - 侧栏顶部页签始终作为全局导航：点击即退出覆盖视图并切到对应工作区。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import App from "./App";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    getToken: vi.fn(() => "tok"),
    setToken: vi.fn(),
    clearToken: vi.fn(),
    fetchProfile: vi.fn(),
    fetchSessions: vi.fn(),
    fetchMessages: vi.fn(),
    fetchTodos: vi.fn(),
    fetchCategories: vi.fn(),
    fetchWikiSpaces: vi.fn(),
    fetchWikiPages: vi.fn(),
    fetchWikiGraph: vi.fn(),
    fetchWikiPage: vi.fn(),
    // 头部 ModelSelect / 未配置 Key 引导
    fetchLlmSettings: vi.fn(),
    fetchLlmModels: vi.fn(),
    // 管理后台（默认概览页）
    fetchAdminOverview: vi.fn(),
    fetchAdminUsage: vi.fn(),
  };
});

const mocked = vi.mocked(api);

const TODO = {
  id: "t1",
  title: "买牛奶",
  status: "pending" as const,
  priority: 3,
  due_date: null,
  category_id: null,
  category_name: null,
  category_color: null,
  tags: [],
};

const WIKI_SPACES = [
  { id: "s1", name: "my-vault", source_type: "local", page_count: 2, last_synced_at: null },
];

describe("App · 管理后台与工作区侧栏", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchProfile.mockResolvedValue({
      id: "u1",
      username: "demo",
      role: "admin",
      session_count: 0,
      message_count: 0,
      todo_count: 1,
      doc_count: 0,
      chunk_count: 0,
    });
    mocked.fetchSessions.mockResolvedValue([]);
    mocked.fetchMessages.mockResolvedValue([]);
    mocked.fetchTodos.mockResolvedValue([TODO]);
    mocked.fetchCategories.mockResolvedValue([]);
    mocked.fetchWikiSpaces.mockResolvedValue(WIKI_SPACES);
    mocked.fetchWikiPages.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mocked.fetchWikiGraph.mockResolvedValue({
      nodes: [],
      edges: [],
      total_nodes: 0,
      truncated: false,
    });
    mocked.fetchLlmSettings.mockResolvedValue({
      base_url: "https://api.deepseek.com",
      model: "deepseek-chat",
      temperature: 0.7,
      max_tokens: 2048,
      api_key_set: true,
      api_key_preview: "sk-****test",
      source: "env",
    });
    mocked.fetchLlmModels.mockResolvedValue({
      models: ["deepseek-chat"],
      current: "deepseek-chat",
      source: "env",
    });
    mocked.fetchAdminOverview.mockResolvedValue({
      users_total: 1,
      users_active: 1,
      users_disabled: 0,
      admins: 1,
      requests_today: 0,
      tokens_in_today: 0,
      tokens_out_today: 0,
      cost_today: 0,
      error_rate_7d: 0,
      latest_eval: null,
    });
    mocked.fetchAdminUsage.mockResolvedValue([]);
  });

  async function openAdmin() {
    fireEvent.click(await screen.findByLabelText("管理后台"));
    await screen.findByText("管理后台"); // 面板标题
    expect(document.querySelector(".admin-body")).not.toBeNull();
  }

  it("管理后台打开时隐藏工作区目录区（不留空白列表）", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: /待办/ }));
    await screen.findByText("买牛奶");
    expect(document.querySelector(".sider-nav")).not.toBeNull();

    await openAdmin();

    expect(document.querySelector(".sider-nav")).toBeNull();
    expect(screen.queryByText("买牛奶")).toBeNull();
  });

  it("覆盖视图内点当前页签：退出管理后台并恢复工作区列表", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: /待办/ }));
    await screen.findByText("买牛奶");

    await openAdmin();

    // 点的是当前已激活的「待办」页签（onChange 不触发，靠 onTabClick 退出）
    fireEvent.click(screen.getByRole("tab", { name: /待办/ }));

    await waitFor(() => expect(document.querySelector(".admin-body")).toBeNull());
    expect(await screen.findByText("买牛奶")).toBeInTheDocument();
  });

  it("覆盖视图内点其它页签：退出管理后台并切到该工作区", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: /Wiki/ }));
    await screen.findByText(/my-vault/);

    await openAdmin();

    fireEvent.click(screen.getByRole("tab", { name: /待办/ }));

    await waitFor(() => expect(document.querySelector(".admin-body")).toBeNull());
    expect(await screen.findByText("买牛奶")).toBeInTheDocument();
    expect(document.querySelector(".sider-nav")).not.toBeNull();
  });

  it("管理后台「返回」：Wiki 目录列表原样恢复", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: /Wiki/ }));
    await screen.findByText(/my-vault/);

    await openAdmin();

    fireEvent.click(screen.getByText("返回"));

    await waitFor(() => expect(document.querySelector(".admin-body")).toBeNull());
    expect(await screen.findByText(/my-vault/)).toBeInTheDocument();
  });
});

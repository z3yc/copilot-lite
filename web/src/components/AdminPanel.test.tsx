/**
 * AdminPanel 测试：概览 KPI、知识库、审计、质量看板 + 返回。全部 mock api。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import AdminPanel from "./AdminPanel";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchAdminOverview: vi.fn(),
    fetchAdminUsage: vi.fn(),
    fetchAdminKnowledge: vi.fn(),
    fetchAdminAudit: vi.fn(),
    fetchAdminEvalRuns: vi.fn(),
    createAdminEvalRun: vi.fn(),
    fetchAdminUsers: vi.fn(),
  };
});

const mocked = vi.mocked(api);

describe("AdminPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchAdminOverview.mockResolvedValue({
      users_total: 7,
      users_active: 6,
      users_disabled: 1,
      admins: 2,
      requests_today: 42,
      tokens_in_today: 1000,
      tokens_out_today: 500,
      cost_today: 0.12,
      error_rate_7d: 0.05,
      latest_eval: {
        id: "r1",
        status: "done",
        trigger: "manual",
        source_scope: "all",
        config_fingerprint: {},
        metrics: { "recall@5": 0.8 },
        total: 10,
        passed: 8,
        progress: 100,
      },
    });
    mocked.fetchAdminUsage.mockResolvedValue([
      { day: "2026-01-01", requests: 10, tokens_in: 100, tokens_out: 50, cost: 0.01, errors: 0 },
    ]);
    mocked.fetchAdminKnowledge.mockResolvedValue({
      documents_total: 5,
      chunks_total: 20,
      failed_documents: 1,
      by_source: [{ source_type: "md", documents: 5, chunks: 20 }],
      wiki_spaces: 1,
      wiki_pages: 3,
      wiki_dangling_links: 2,
      spaces: [
        { id: "s1", name: "空间A", page_count: 3, last_synced_at: "2026-01-01T00:00:00" },
      ],
    });
    mocked.fetchAdminAudit.mockResolvedValue({
      items: [
        {
          id: "a1",
          action: "user.create",
          result: "ok",
          resource_type: "user",
          resource_id: "u1",
          request_id: "req-1",
          meta: {},
          created_at: "2026-01-01T00:00:00",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mocked.fetchAdminEvalRuns.mockResolvedValue({
      items: [
        {
          id: "r1",
          status: "done",
          trigger: "manual",
          source_scope: "all",
          config_fingerprint: {},
          metrics: { "recall@5": 0.8 },
          total: 10,
          passed: 8,
          progress: 100,
          created_at: "2026-01-01T00:00:00",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mocked.createAdminEvalRun.mockResolvedValue({
      id: "r2",
      status: "queued",
      trigger: "manual",
      source_scope: "all",
      config_fingerprint: {},
      metrics: {},
      total: 0,
      passed: 0,
      progress: 0,
    });
    mocked.fetchAdminUsers.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  it("概览展示 KPI 与最新评测", async () => {
    render(<AdminPanel onBack={() => {}} />);
    expect(await screen.findByText("用户总数")).toBeInTheDocument();
    expect(screen.getByText("今日请求")).toBeInTheDocument();
    expect(screen.getByText("近 7 日错误率")).toBeInTheDocument();
    expect(screen.getByText("最新评测")).toBeInTheDocument();
    expect(screen.getByText("recall@5")).toBeInTheDocument();
  });

  it("知识库页展示来源切片与 Wiki 统计", async () => {
    render(<AdminPanel onBack={() => {}} />);
    await screen.findByText("用户总数");
    fireEvent.click(screen.getByRole("tab", { name: /知识库/ }));
    expect(await screen.findByText("文档总数")).toBeInTheDocument();
    expect(screen.getByText("悬空链接")).toBeInTheDocument();
    expect(await screen.findByText("空间A")).toBeInTheDocument();
  });

  it("审计页展示记录并可串 request_id", async () => {
    render(<AdminPanel onBack={() => {}} />);
    await screen.findByText("用户总数");
    fireEvent.click(screen.getByRole("tab", { name: /审计日志/ }));
    expect(await screen.findByText("user.create")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("按 request_id 串链路")).toBeInTheDocument();
  });

  it("质量看板触发评测调用 createAdminEvalRun", async () => {
    render(<AdminPanel onBack={() => {}} />);
    await screen.findByText("用户总数");
    fireEvent.click(screen.getByRole("tab", { name: /质量看板/ }));
    fireEvent.click(await screen.findByRole("button", { name: /运行评测/ }));
    await waitFor(() =>
      expect(mocked.createAdminEvalRun).toHaveBeenCalledWith({
        source_scope: "all",
        trigger: "manual",
      })
    );
  });

  it("点击返回触发 onBack", async () => {
    const onBack = vi.fn();
    render(<AdminPanel onBack={onBack} />);
    await screen.findByText("用户总数");
    fireEvent.click(screen.getByRole("button", { name: /返回/ }));
    expect(onBack).toHaveBeenCalled();
  });
});

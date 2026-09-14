/**
 * ProfilePage「模型设置」测试：用表单里未保存的 Key 拉取模型列表并回填。
 * 全部 mock api，不触网。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import ProfilePage from "./ProfilePage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchProfile: vi.fn(),
    fetchSessions: vi.fn(),
    fetchTodos: vi.fn(),
    fetchMemories: vi.fn(),
    fetchLlmSettings: vi.fn(),
    fetchLlmModels: vi.fn(),
    fetchLlmModelsWithKey: vi.fn(),
    saveLlmSettings: vi.fn(),
    testLlmSettings: vi.fn(),
    deleteLlmSettings: vi.fn(),
    changePassword: vi.fn(),
    deleteSession: vi.fn(),
    deleteTodo: vi.fn(),
    deleteMemory: vi.fn(),
    updateMemory: vi.fn(),
    updateTodo: vi.fn(),
  };
});

const mocked = vi.mocked(api);

describe("ProfilePage 模型设置", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchProfile.mockResolvedValue({
      id: "u1",
      username: "tester",
      role: "user",
      session_count: 0,
      message_count: 0,
      todo_count: 0,
      doc_count: 0,
      chunk_count: 0,
    });
    mocked.fetchSessions.mockResolvedValue([]);
    mocked.fetchTodos.mockResolvedValue([]);
    mocked.fetchMemories.mockResolvedValue([]);
    mocked.fetchLlmSettings.mockResolvedValue({
      base_url: "https://api.deepseek.com",
      model: "deepseek-chat",
      temperature: 0.7,
      max_tokens: 2048,
      api_key_set: false,
      api_key_preview: "",
      source: "none",
    });
    mocked.fetchLlmModels.mockResolvedValue({
      models: [],
      current: "deepseek-chat",
      source: "none",
    });
    mocked.fetchLlmModelsWithKey.mockResolvedValue({
      models: ["deepseek-chat", "deepseek-reasoner"],
      current: "deepseek-chat",
      source: "user",
    });
  });

  it("点击「获取模型」用未保存的 Key 拉取列表", async () => {
    render(<ProfilePage onBack={() => {}} onOpenSession={() => {}} initialTab="model" />);

    // 等配置表单回填完成（base_url 出现在输入框）
    await waitFor(() =>
      expect(screen.getByDisplayValue("https://api.deepseek.com")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByPlaceholderText("sk-..."), {
      target: { value: "sk-my-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: /获取模型/ }));

    await waitFor(() =>
      expect(mocked.fetchLlmModelsWithKey).toHaveBeenCalledWith({
        base_url: "https://api.deepseek.com",
        api_key: "sk-my-key",
      })
    );

    // 拉到候选后下拉应自动展开，且可选择
    const option = await screen.findByText("deepseek-reasoner");
    fireEvent.click(option);
    await waitFor(() =>
      expect(screen.getByDisplayValue("deepseek-reasoner")).toBeInTheDocument()
    );
  });
});

/**
 * ChatPanel 组件测试：消息渲染、空状态、发送流程（mock api 模块，
 * streamChat 模拟 SSE 事件流驱动增量渲染）。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import type { ChatMessage } from "../types";
import ChatPanel from "./ChatPanel";

vi.mock("../api", () => ({
  createSession: vi.fn(),
  fetchSessionFiles: vi.fn(),
  fetchMessages: vi.fn(),
  confirmChat: vi.fn(),
  streamChat: vi.fn(),
  uploadSessionFile: vi.fn(),
  deleteSessionFile: vi.fn(),
  // 头部 ModelSelect 依赖
  fetchLlmSettings: vi.fn(),
  fetchLlmModels: vi.fn(),
  saveLlmSettings: vi.fn(),
}));

const mocked = vi.mocked(api);

function renderPanel(overrides?: Partial<React.ComponentProps<typeof ChatPanel>>) {
  const props = {
    sessionId: null,
    initialMessages: [] as ChatMessage[],
    onSessionCreated: vi.fn(),
    onNewSession: vi.fn(),
    busy: false,
    setBusy: vi.fn(),
    ...overrides,
  };
  return { ...render(<ChatPanel {...props} />), props };
}

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks(); // 隔离用例间的调用记录与实现
    mocked.fetchSessionFiles.mockResolvedValue([]);
    mocked.fetchMessages.mockResolvedValue([]);
    // 默认：使用环境变量默认模型 → ModelSelect 只读，不触发额外交互
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
  });

  it("渲染历史消息与标题", () => {
    renderPanel({
      initialMessages: [
        { role: "user", content: "你好" },
        { role: "assistant", content: "我是青木" },
      ],
    });
    expect(screen.getByText("Copilot-Lite · 青木")).toBeInTheDocument();
    expect(screen.getByText("你好")).toBeInTheDocument();
    expect(screen.getByText("我是青木")).toBeInTheDocument();
  });

  it("传入 sessionTitle 时头部回显会话标题（否则回退品牌名）", () => {
    renderPanel({ sessionTitle: "面试准备" });
    expect(screen.getByText("面试准备")).toBeInTheDocument();
    expect(screen.queryByText("Copilot-Lite · 青木")).not.toBeInTheDocument();
  });

  it("无消息时展示空状态引导", () => {
    renderPanel();
    expect(screen.getByText(/你好！我是青木/)).toBeInTheDocument();
  });

  it("渲染引用来源", () => {
    renderPanel({
      initialMessages: [
        {
          role: "assistant",
          content: "答案 [1]",
          extra: {
            citations: [
              { index: 1, chunk_id: "c1", source: "文档X > 第一章", snippet: "内容A" },
            ],
          },
        },
      ],
    });
    expect(screen.getByText("来源：")).toBeInTheDocument();
    expect(screen.getByText("[1]")).toBeInTheDocument();
  });

  it("有待确认操作时展示确认按钮并调用 confirmChat", async () => {
    mocked.confirmChat.mockResolvedValue({ reply: "已执行" });
    renderPanel({
      sessionId: "s1",
      initialMessages: [
        {
          role: "assistant",
          content: "需要确认",
          extra: {
            pending_confirmation: [
              { name: "todo_delete", arguments: '{"todo_id":"x"}' },
            ],
          },
        },
      ],
    });
    expect(screen.getByText(/需要你确认/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /确认执行/ }));
    await waitFor(() =>
      expect(mocked.confirmChat).toHaveBeenCalledWith("s1", true)
    );
    expect(await screen.findByText("已执行")).toBeInTheDocument();
  });

  it("发送消息：调用 streamChat，chunk 增量渲染，完成后恢复 busy", async () => {
    const setBusy = vi.fn();
    const onSessionCreated = vi.fn();
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      handlers.onSession("s-new");
      handlers.onChunk("你");
      handlers.onChunk("好");
      handlers.onDone();
    });

    renderPanel({ setBusy, onSessionCreated });

    const textarea = screen.getByPlaceholderText(/输入消息/);
    fireEvent.change(textarea, { target: { value: "测试问题" } });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() =>
      expect(mocked.streamChat).toHaveBeenCalledWith("测试问题", null, expect.any(Object))
    );
    await waitFor(() => expect(screen.getByText("你好")).toBeInTheDocument());
    expect(onSessionCreated).toHaveBeenCalledWith("s-new");
    expect(setBusy).toHaveBeenCalledWith(true);
    expect(setBusy).toHaveBeenCalledWith(false);
  });

  it("流式出错时在气泡中展示错误并恢复 busy", async () => {
    const setBusy = vi.fn();
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      handlers.onError("网络中断");
    });

    renderPanel({ setBusy });

    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => expect(screen.getByText(/网络中断/)).toBeInTheDocument());
    expect(setBusy).toHaveBeenCalledWith(false);
  });

  it("空输入不发送（发送按钮禁用）", () => {
    renderPanel();
    const sendBtn = screen.getByRole("button", { name: /发送/ });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(true);
    expect(mocked.streamChat).not.toHaveBeenCalled();
  });

  it("streamChat 异常时 finally 复位 busy（防 UI 永久卡死）", async () => {
    const setBusy = vi.fn();
    mocked.streamChat.mockRejectedValue(new Error("boom"));

    renderPanel({ setBusy });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => expect(setBusy).toHaveBeenCalledWith(false));
  });

  it("busy 时展示停止按钮（发送按钮隐藏）", () => {
    renderPanel({ busy: true });
    expect(screen.getByRole("button", { name: /停止/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /发送/ })).not.toBeInTheDocument();
  });
});

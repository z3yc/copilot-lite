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
  streamChat: vi.fn(),
  uploadSessionFile: vi.fn(),
  deleteSessionFile: vi.fn(),
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

  it("无消息时展示空状态引导", () => {
    renderPanel();
    expect(screen.getByText(/你好！我是青木/)).toBeInTheDocument();
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
});

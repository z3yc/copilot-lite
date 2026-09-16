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

/** 共享空数组：模拟父组件 messages state 在「建会话」过程中引用不变（App.tsx 只 setSessionId）。
 *  冻结以在测试间意外原地修改时尽早报错。 */
const EMPTY_MESSAGES = Object.freeze([]) as unknown as ChatMessage[];

function panelProps(overrides?: Partial<React.ComponentProps<typeof ChatPanel>>) {
  const props = {
    sessionId: null,
    initialMessages: EMPTY_MESSAGES,
    onSessionCreated: vi.fn(),
    onNewSession: vi.fn(),
    busy: false,
    setBusy: vi.fn(),
    ...overrides,
  };
  return props;
}

function renderPanel(overrides?: Partial<React.ComponentProps<typeof ChatPanel>>) {
  const props = panelProps(overrides);
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

  it("Wiki 引用显示类型标签并可点击跳转", async () => {
    const onOpenCitation = vi.fn();
    const citation = {
      index: 1,
      chunk_id: "c1",
      document_id: "d1",
      source: "Wiki / 我的笔记 / 方法论",
      source_kind: "wiki" as const,
      wiki: {
        page_id: "p1",
        space_id: "s1",
        space_name: "我的笔记",
        rel_path: "笔记/方法论.md",
      },
    };
    renderPanel({
      onOpenCitation,
      initialMessages: [
        { role: "assistant", content: "答案 [1]", extra: { citations: [citation] } },
      ],
    });
    const link = screen.getByRole("button", { name: "查看来源 1" });
    expect(link).toHaveTextContent("[1]");
    expect(link).toHaveAttribute("title", "Wiki / 我的笔记 / 方法论");
    fireEvent.click(link);
    expect(onOpenCitation).toHaveBeenCalledTimes(1);
    expect(onOpenCitation.mock.calls[0][0].wiki.page_id).toBe("p1");
  });

  it("旧格式引用（无跳转目标）只做文本展示，不给按钮语义", () => {
    const onOpenCitation = vi.fn();
    renderPanel({
      onOpenCitation,
      initialMessages: [
        {
          role: "assistant",
          content: "答案 [1]",
          extra: {
            citations: [{ index: 1, chunk_id: "c1", source: "旧文档 > 第一章" }],
          },
        },
      ],
    });
    expect(screen.queryByRole("button", { name: "查看来源 1" })).not.toBeInTheDocument();
    expect(screen.getByTitle("旧文档 > 第一章")).toHaveTextContent("[1]");
    expect(onOpenCitation).not.toHaveBeenCalled();
  });

  it("wiki 引用缺失 page_id 时不可点，且不误跳知识库", () => {
    const onOpenCitation = vi.fn();
    renderPanel({
      onOpenCitation,
      initialMessages: [
        {
          role: "assistant",
          content: "答案 [1]",
          extra: {
            citations: [
              {
                index: 1,
                chunk_id: "c1",
                document_id: "d1",
                source: "Wiki / 我的笔记 / 已删页面",
                source_kind: "wiki" as const,
              },
            ],
          },
        },
      ],
    });
    // 关键回归：有 document_id 也不能降级成文档按钮（否则会跳到知识库里的错文档）
    expect(screen.queryByRole("button", { name: "查看来源 1" })).not.toBeInTheDocument();
    expect(screen.getByTitle("Wiki / 我的笔记 / 已删页面（页面已删除或暂不可用）")).toHaveTextContent(
      "[1]"
    );
    expect(onOpenCitation).not.toHaveBeenCalled();
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

  it("done 事件带 trajectory 时在气泡内渲染轨迹面板", async () => {
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      handlers.onChunk("回答");
      handlers.onDone({
        trajectory: {
          engine: "langgraph",
          total_ms: 88,
          truncated: false,
          steps: [{ type: "route", route: "tools", source: "keyword", ms: 5 }],
        },
      });
    });

    renderPanel();
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "测试问题" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText(/本次回答轨迹/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/本次回答轨迹/));
    expect(screen.getByText(/关键词兜底/)).toBeInTheDocument();
  });

  it("历史消息自带 trajectory 时也能渲染（刷新后回放）", () => {
    renderPanel({
      initialMessages: [
        {
          role: "assistant",
          content: "答案",
          extra: {
            trajectory: {
              engine: "handwritten",
              total_ms: 30,
              truncated: false,
              steps: [{ type: "node", node: "orchestrator" }],
            },
          },
        },
      ],
    });
    expect(screen.getByText(/本次回答轨迹/)).toBeInTheDocument();
  });

  it("done 无 trajectory 时仍复位 busy 且不渲染面板", async () => {
    const setBusy = vi.fn();
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      handlers.onChunk("回答");
      handlers.onDone();
    });

    renderPanel({ setBusy });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => expect(setBusy).toHaveBeenCalledWith(false));
    expect(screen.queryByText(/本次回答轨迹/)).not.toBeInTheDocument();
  });

  it("新会话首条消息不被自身的会话创建取消（防「已停止生成」）", async () => {
    let signal: AbortSignal | undefined;
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      signal = handlers.signal;
      handlers.onSession("s-new");
      handlers.onChunk("回答");
      await new Promise(() => {}); // 流保持进行中，rerender 时 abortRef 仍有效
    });

    const { rerender } = renderPanel({ sessionId: null });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "第一条" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());
    // 模拟父组件收到 onSessionCreated 后把 sessionId 传下来
    rerender(<ChatPanel {...panelProps({ sessionId: "s-new" })} />);

    expect(signal?.aborted).toBe(false);
    await waitFor(() => expect(screen.getByText("回答")).toBeInTheDocument());
  });

  it("新会话建出来前点「新建会话」会取消进行中的流（sessionId 仍为 null）", async () => {
    let signal: AbortSignal | undefined;
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      signal = handlers.signal;
      // 不发 onSession：模拟 SSE session 帧尚未到达，归属仍为 null
      await new Promise(() => {});
    });

    const { rerender } = renderPanel({ sessionId: null });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "第一条" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());

    // 模拟 App.newSession：sessionId 仍为 null（切换 effect 不触发），messages 换成新空数组
    rerender(<ChatPanel {...panelProps({ sessionId: null, initialMessages: [] })} />);

    await waitFor(() => expect(signal?.aborted).toBe(true));
  });

  it("真正切换会话时仍会取消进行中的流（保住原意图）", async () => {
    let signal: AbortSignal | undefined;
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      signal = handlers.signal;
      handlers.onSession("s-1");
      await new Promise(() => {}); // 永不结束，模拟进行中
    });

    const { rerender } = renderPanel({ sessionId: "s-1" });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());

    rerender(<ChatPanel {...panelProps({ sessionId: "s-2" })} />);
    await waitFor(() => expect(signal?.aborted).toBe(true));
  });

  it("新建/切换会话中止流时不残留「生成出错」气泡（busy 仍复位）", async () => {
    const setBusy = vi.fn();
    let deliveredError = false;
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      const signal = handlers.signal!;
      await new Promise<void>((resolve) => {
        const onAbort = () => {
          // 真实 fetch 的 abort 拒绝是异步投递的：让「清空列表」的 state 更新先生效
          queueMicrotask(() => {
            deliveredError = true;
            handlers.onError("已停止生成");
            resolve();
          });
        };
        if (signal.aborted) onAbort();
        else signal.addEventListener("abort", onAbort, { once: true });
      });
    });

    const { rerender } = renderPanel({ sessionId: null, setBusy });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "第一条" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());

    // 模拟 App.newSession：sessionId 仍为 null，messages 换成新空数组（触发中止）
    rerender(<ChatPanel {...panelProps({ sessionId: null, initialMessages: [] })} />);

    await waitFor(() => expect(deliveredError).toBe(true));
    expect(screen.queryByText(/生成出错/)).not.toBeInTheDocument();
    expect(setBusy).toHaveBeenCalledWith(false);
  });

  it("点「停止」中止流时仍展示「生成出错：已停止生成」", async () => {
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      const signal = handlers.signal!;
      await new Promise<void>((resolve) => {
        signal.addEventListener(
          "abort",
          () => {
            queueMicrotask(() => {
              handlers.onError("已停止生成");
              resolve();
            });
          },
          { once: true }
        );
      });
    });

    const { rerender } = renderPanel({ sessionId: "s1" });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());

    // 父组件把 busy 置真 → 停止按钮出现（复用内置的 EMPTY_MESSAGES，避免误触清空 effect）
    rerender(<ChatPanel {...panelProps({ sessionId: "s1", busy: true })} />);
    fireEvent.click(screen.getByRole("button", { name: /停止/ }));

    expect(await screen.findByText(/生成出错：已停止生成/)).toBeInTheDocument();
  });
});

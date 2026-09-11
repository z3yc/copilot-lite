/**
 * api.ts 单元测试：token 管理、request 封装（认证头/401/错误）、
 * URL 拼接、SSE 流式解析（跨 read 缓冲/事件分发/错误回调）。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearToken,
  fetchDocs,
  fetchSessions,
  fetchTodos,
  getToken,
  setToken,
  streamChat,
  type StreamHandlers,
} from "./api";

function okJson(data: unknown) {
  return {
    status: 200,
    ok: true,
    json: async () => ({ code: 0, message: "ok", data }),
    text: async () => "",
  };
}

describe("token 管理", () => {
  it("setToken / getToken / clearToken 读写 localStorage", () => {
    expect(getToken()).toBeNull();
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    clearToken();
    expect(getToken()).toBeNull();
  });
});

describe("request 封装", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("自动携带 Authorization 头并解析 JSON", async () => {
    setToken("tok123");
    fetchMock.mockResolvedValue(
      okJson({ items: [{ id: "s1" }], total: 1, page: 1, page_size: 20 })
    );

    const data = await fetchSessions();
    expect(data).toEqual([{ id: "s1" }]);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/v1/sessions");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok123");
  });

  it("401 时清除令牌并派发 auth-expired 事件", async () => {
    setToken("expired");
    const listener = vi.fn();
    window.addEventListener("auth-expired", listener);
    fetchMock.mockResolvedValue({ status: 401, ok: false, text: async () => "unauthorized" });

    await expect(fetchSessions()).rejects.toThrow("登录已过期");
    expect(getToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener("auth-expired", listener);
  });

  it("非 2xx 抛出带状态码的错误信息", async () => {
    fetchMock.mockResolvedValue({ status: 500, ok: false, text: async () => "boom" });
    await expect(fetchSessions()).rejects.toThrow("请求失败 500");
  });

  it("非 2xx 优先使用后端统一错误体的 message", async () => {
    fetchMock.mockResolvedValue({
      status: 404,
      ok: false,
      json: async () => ({ code: 2001, message: "会话不存在", data: null }),
      text: async () => "",
    });
    await expect(fetchSessions()).rejects.toThrow("会话不存在");
  });

  it("信封 code!=0 时抛出 message", async () => {
    fetchMock.mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ code: 2001, message: "会话不存在", data: null }),
      text: async () => "",
    });
    await expect(fetchSessions()).rejects.toThrow("会话不存在");
  });

  it("fetchTodos 按参数拼接查询串", async () => {
    fetchMock.mockResolvedValue(
      okJson({ items: [], total: 0, page: 1, page_size: 20 })
    );
    await fetchTodos({ status: "open", tag: "urgent" });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/v1/todos?");
    expect(url).toContain("status=open");
    expect(url).toContain("tag=urgent");
  });

  it("fetchDocs 拼接 q 与 type 参数", async () => {
    fetchMock.mockResolvedValue(
      okJson({ items: [], total: 0, page: 1, page_size: 20 })
    );
    await fetchDocs("笔记", "md");

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/v1/documents?");
    expect(url).toContain("q=");
    expect(url).toContain("type=md");
  });
});

describe("streamChat SSE 解析", () => {
  type HandlerMocks = Omit<
    Record<keyof StreamHandlers, ReturnType<typeof vi.fn>>,
    "signal"
  > & { signal?: AbortSignal };
  const handlers = (): HandlerMocks => ({
    onSession: vi.fn(),
    onChunk: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
    onPending: vi.fn(),
    signal: undefined,
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("解析完整事件序列，且跨 read 分片的 JSON 能正确拼接", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: session\ndata: {"session_id": "s1"}\n\n'));
        // 故意把一个 chunk 事件拆成两段 enqueue，验证 buffer 拼接
        controller.enqueue(encoder.encode('event: chunk\ndata: {"text": "你'));
        controller.enqueue(encoder.encode('好"}\n\n'));
        controller.enqueue(encoder.encode('event: chunk\ndata: {"text": "世界"}\n\n'));
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

    const h = handlers();
    await streamChat("你好", null, h);

    expect(h.onSession).toHaveBeenCalledWith("s1");
    expect(h.onChunk.mock.calls.map((c) => c[0])).toEqual(["你好", "世界"]);
    expect(h.onDone).toHaveBeenCalledTimes(1);
    expect(h.onError).not.toHaveBeenCalled();
  });

  it("HTTP 非 2xx 时回调 onError 并附状态码", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("内部错误", { status: 500 })));

    const h = handlers();
    await streamChat("hi", null, h);

    expect(h.onError).toHaveBeenCalledWith(expect.stringContaining("请求失败 500"));
    expect(h.onSession).not.toHaveBeenCalled();
  });

  it("error 事件透传后端 detail", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: error\ndata: {"detail": "触发限流"}\n\n'));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

    const h = handlers();
    await streamChat("hi", null, h);

    expect(h.onError).toHaveBeenCalledWith("触发限流");
  });

  it("流结束残留未闭合事件时也能分发（尾部 buffer）", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        // 没有结尾 \n\n，依赖尾部 buffer 兜底分发
        controller.enqueue(encoder.encode('event: chunk\ndata: {"text": "尾部"}'));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

    const h = handlers();
    await streamChat("hi", null, h);

    expect(h.onChunk).toHaveBeenCalledWith("尾部");
  });

  it("携带 Authorization 头与请求体（修复流式对话 401）", async () => {
    setToken("tok-sse");
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const h = handlers();
    await streamChat("你好", "s1", h);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/v1/chat/stream");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok-sse");
    expect(String(init.body)).toContain("你好");
    expect(String(init.body)).toContain("s1");
    expect(h.onDone).toHaveBeenCalledTimes(1);
  });

  it("401 时清除令牌、派发 auth-expired 并提示重新登录", async () => {
    setToken("expired");
    const listener = vi.fn();
    window.addEventListener("auth-expired", listener);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"detail":"未登录"}', { status: 401 }))
    );

    const h = handlers();
    await streamChat("hi", null, h);

    expect(getToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(h.onError).toHaveBeenCalledWith("登录已过期，请重新登录");
    window.removeEventListener("auth-expired", listener);
  });

  it("跳过 SSE 心跳注释行（: ping），不误触发事件", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(": ping\n\n"));
        controller.enqueue(encoder.encode('event: chunk\ndata: {"text": "正常"}\n\n'));
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

    const h = handlers();
    await streamChat("hi", null, h);

    expect(h.onChunk).toHaveBeenCalledWith("正常");
    expect(h.onDone).toHaveBeenCalledTimes(1);
    expect(h.onError).not.toHaveBeenCalled();
  });

  it("畸形 JSON 分片被丢弃，不杀死整个流", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("event: chunk\ndata: {坏数据}\n\n"));
        controller.enqueue(encoder.encode('event: chunk\ndata: {"text": "好数据"}\n\n'));
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

    const h = handlers();
    await streamChat("hi", null, h);

    expect(h.onChunk).toHaveBeenCalledWith("好数据");
    expect(h.onDone).toHaveBeenCalledTimes(1);
  });

  it("请求被中断（AbortError）时回调 onError 且不挂死", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(Object.assign(new Error("aborted"), { name: "AbortError" }))
    );

    const h = handlers();
    await streamChat("hi", null, h);

    expect(h.onError).toHaveBeenCalledWith("已停止生成");
    expect(h.onSession).not.toHaveBeenCalled();
  });
});

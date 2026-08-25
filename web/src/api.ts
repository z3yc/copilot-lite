import type { ChatMessage, DocItem, Session } from "./types";

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`请求失败 ${resp.status}: ${detail.slice(0, 200)}`);
  }
  return resp.json() as Promise<T>;
}

// ---- 会话 ----
export const fetchSessions = () => request<Session[]>("/sessions");
export const fetchMessages = (sessionId: string) =>
  request<ChatMessage[]>(`/sessions/${sessionId}/messages`);
export const deleteSession = (sessionId: string) =>
  request<{ deleted: string }>(`/sessions/${sessionId}`, { method: "DELETE" });

// ---- 文档 ----
export const fetchDocs = () => request<DocItem[]>("/documents");
export const deleteDoc = (docId: string) =>
  request<{ deleted: string }>(`/documents/${docId}`, { method: "DELETE" });

export async function uploadDocs(files: File[]): Promise<DocItem[]> {
  const results: DocItem[] = [];
  for (const file of files) {
    const form = new FormData();
    form.append("file", file);
    const item = await request<DocItem>("/documents/upload", { method: "POST", body: form });
    results.push(item);
  }
  return results;
}

// ---- SSE 流式对话 ----
export interface StreamHandlers {
  onSession: (sessionId: string) => void;
  onChunk: (text: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export async function streamChat(
  message: string,
  sessionId: string | null,
  handlers: StreamHandlers
): Promise<void> {
  const resp = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!resp.ok || !resp.body) {
    const detail = await resp.text();
    handlers.onError(`请求失败 ${resp.status}: ${detail.slice(0, 200)}`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (part: string) => {
    let event = "message";
    let data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (!data) return;
    const payload = JSON.parse(data);
    if (event === "session") handlers.onSession(payload.session_id);
    else if (event === "chunk") handlers.onChunk(payload.text);
    else if (event === "error") handlers.onError(payload.detail);
    else if (event === "done") handlers.onDone();
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) dispatch(part);
  }
  if (buffer.trim()) dispatch(buffer);
}

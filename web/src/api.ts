import type {
  ChatMessage,
  DocDetail,
  DocItem,
  Profile,
  Session,
  SessionFile,
  TodoItem,
} from "./types";

const BASE = "/api/v1";
const TOKEN_KEY = "kb-token";

// ---- 认证令牌管理 ----
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(`${BASE}${path}`, { ...init, headers });
  if (resp.status === 401) {
    // 登录过期：清除令牌并通知应用回到登录页
    clearToken();
    window.dispatchEvent(new Event("auth-expired"));
    throw new Error("登录已过期，请重新登录");
  }
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`请求失败 ${resp.status}: ${detail.slice(0, 200)}`);
  }
  return resp.json() as Promise<T>;
}

// ---- 认证 ----
export interface AuthResp {
  token: string;
  user: { id: string; username: string; role: string };
}

export const login = (username: string, password: string) =>
  request<AuthResp>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
export const register = (username: string, password: string) =>
  request<AuthResp>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
export const fetchProfile = () => request<Profile>("/auth/profile");
export const changePassword = (oldPassword: string, newPassword: string) =>
  request<{ ok: boolean; message: string }>("/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });

// ---- 会话 ----
export const fetchSessions = () => request<Session[]>("/sessions");
export const fetchMessages = (sessionId: string) =>
  request<ChatMessage[]>(`/sessions/${sessionId}/messages`);
export const deleteSession = (sessionId: string) =>
  request<{ deleted: string }>(`/sessions/${sessionId}`, { method: "DELETE" });

// ---- 待办 ----
export const fetchTodos = (status?: string) =>
  request<TodoItem[]>(`/todos${status ? `?status=${status}` : ""}`);
export const updateTodo = (id: string, status: string) =>
  request<TodoItem>(`/todos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
export const deleteTodo = (id: string) =>
  request<{ deleted: string }>(`/todos/${id}`, { method: "DELETE" });

// ---- 文档 ----
export const fetchDocs = (q?: string, type?: string) => {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (type) params.set("type", type);
  const qs = params.toString();
  return request<DocItem[]>(`/documents${qs ? `?${qs}` : ""}`);
};
export const fetchDocDetail = (docId: string) =>
  request<DocDetail>(`/documents/${docId}/chunks`);
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

// ---- 会话附件（仅本次对话，不进知识库）----
export const createSession = () =>
  request<Session>("/sessions", { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } });
export const fetchSessionFiles = (sessionId: string) =>
  request<SessionFile[]>(`/sessions/${sessionId}/files`);
export const deleteSessionFile = (sessionId: string, fileId: string) =>
  request<{ deleted: string }>(`/sessions/${sessionId}/files/${fileId}`, { method: "DELETE" });

export async function uploadSessionFile(sessionId: string, file: File): Promise<SessionFile> {
  const form = new FormData();
  form.append("file", file);
  return request<SessionFile>(`/sessions/${sessionId}/files`, { method: "POST", body: form });
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

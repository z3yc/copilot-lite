import type {
  AdminAuditItem,
  AdminEvalRun,
  AdminKnowledge,
  AdminOverview,
  AdminUsagePoint,
  AdminUser,
  AdminUserDetail,
  Category,
  ChatMessage,
  DocDetail,
  DocItem,
  JobInfo,
  LLMSettings,
  MemoryItem,
  PendingAction,
  Profile,
  Session,
  SessionFile,
  TodoItem,
  TrashItem,
  WikiGraph,
  WikiPage,
  WikiPageDetail,
  WikiSpace,
  WikiSyncResponse,
} from "./types";

const BASE = "/api/v1";
const TOKEN_KEY = "kb-token";

// ---- 认证令牌管理 ----
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

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
    // 后端统一错误体 {code,message,data}；非 JSON 时回退状态码提示
    let message = `请求失败 ${resp.status}`;
    try {
      const body = await resp.json();
      if (body && typeof body.message === "string" && body.message) {
        message = body.message;
      }
    } catch {
      // 忽略：保留状态码提示
    }
    throw new Error(message);
  }
  const body = (await resp.json()) as Envelope<T> | T;
  // 统一响应结构：解包 data；兼容非信封响应
  if (body && typeof body === "object" && "code" in (body as Record<string, unknown>)) {
    const env = body as Envelope<T>;
    if (env.code !== 0) throw new Error(env.message || "请求失败");
    return env.data;
  }
  return body as T;
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

// ---- 长期记忆 ----
export const fetchMemories = () => request<MemoryItem[]>("/memories");
export const updateMemory = (id: string, fact: string, category: string) =>
  request<MemoryItem>(`/memories/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fact, category }),
  });
export const deleteMemory = (id: string) =>
  request<{ deleted: string }>(`/memories/${id}`, { method: "DELETE" });

// ---- 分页 ----
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---- 会话 ----
export const fetchSessions = async (q?: string): Promise<Session[]> =>
  (
    await request<Page<Session>>(
      `/sessions${q ? `?q=${encodeURIComponent(q)}` : ""}`
    )
  ).items;
export const fetchMessages = (sessionId: string) =>
  request<ChatMessage[]>(`/sessions/${sessionId}/messages`);
export const deleteSession = (sessionId: string) =>
  request<{ deleted: string }>(`/sessions/${sessionId}`, { method: "DELETE" });
export const renameSession = (sessionId: string, title: string) =>
  request<Session>(`/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });

/** 导出会话 Markdown（带认证的裸 fetch，不走 JSON 解析）。 */
export async function exportSessionMarkdown(sessionId: string): Promise<string> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const resp = await fetch(`${BASE}/sessions/${sessionId}/export`, { headers });
  if (!resp.ok) throw new Error(`导出失败 ${resp.status}`);
  return resp.text();
}

// ---- 待办 ----
export interface TodoPayload {
  title?: string;
  status?: string;
  priority?: number;
  due_date?: string | null;
  category_id?: string | null;
  tags?: string[];
}

export const fetchTodos = async (params?: {
  status?: string;
  category_id?: string;
  tag?: string;
}): Promise<TodoItem[]> => {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.category_id) qs.set("category_id", params.category_id);
  if (params?.tag) qs.set("tag", params.tag);
  const s = qs.toString();
  return (await request<Page<TodoItem>>(`/todos${s ? `?${s}` : ""}`)).items;
};
export const fetchCategories = () => request<Category[]>(`/todos/categories`);
export const createTodo = (data: TodoPayload) =>
  request<TodoItem>("/todos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
export const updateTodo = (id: string, data: TodoPayload) =>
  request<TodoItem>(`/todos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
export const deleteTodo = (id: string) =>
  request<{ deleted: string }>(`/todos/${id}`, { method: "DELETE" });
export const aiCreateTodo = (text: string) =>
  request<TodoItem>("/todos/ai-create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

// ---- 文档 ----
export const fetchDocs = async (q?: string, type?: string): Promise<DocItem[]> => {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (type) params.set("type", type);
  const qs = params.toString();
  return (await request<Page<DocItem>>(`/documents${qs ? `?${qs}` : ""}`)).items;
};
export const fetchDocDetail = (docId: string) =>
  request<DocDetail>(`/documents/${docId}/chunks`);
export const deleteDoc = (docId: string) =>
  request<{ deleted: string }>(`/documents/${docId}`, { method: "DELETE" });
export const retryDoc = (docId: string) =>
  request<DocItem>(`/documents/${docId}/retry`, { method: "POST" });

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
// ---- 回收站（软删除）----
export const fetchTrash = () => request<TrashItem[]>("/trash");
export const restoreTrashItem = (type: string, id: string) =>
  request<{ restored: string; type: string }>(`/trash/${type}/${id}/restore`, {
    method: "POST",
  });

// ---- Wiki ----
export const fetchWikiSpaces = () => request<WikiSpace[]>("/wiki/spaces");

export const createWikiSpace = (
  name: string,
  source_type: "upload" | "local" = "upload",
  server_path?: string
) =>
  request<WikiSpace>("/wiki/spaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, source_type, server_path }),
  });

export const deleteWikiSpace = (id: string) =>
  request<{ deleted: string }>(`/wiki/spaces/${id}`, { method: "DELETE" });

export const syncWikiSpace = (id: string) =>
  request<WikiSyncResponse>(`/wiki/spaces/${id}/sync`, { method: "POST" });

export async function importWikiZip(
  spaceId: string,
  file: File
): Promise<WikiSyncResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<WikiSyncResponse>(`/wiki/spaces/${spaceId}/import`, {
    method: "POST",
    body: form,
  });
}

/** 导入单/多文件（或文件夹，带相对路径）；paths 与 files 同序。 */
export async function importWikiFiles(
  spaceId: string,
  files: File[],
  paths: string[]
): Promise<WikiSyncResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("paths", JSON.stringify(paths));
  return request<WikiSyncResponse>(`/wiki/spaces/${spaceId}/import-files`, {
    method: "POST",
    body: form,
  });
}

// ---- 通用后台作业（J1）----
export const fetchJob = (id: string, signal?: AbortSignal) =>
  request<JobInfo>(`/jobs/${id}`, { signal });

/**
 * 轮询作业至终态（done / dead）。
 *
 * - 可取消：传 `signal` 后请求与轮询可被中止（AGENTS §5：异步必须可取消）；
 * - 有上限：超过 `timeoutMs` 抛错，避免无限轮询。
 */
export async function waitForJob(
  jobId: string,
  opts: { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal } = {}
): Promise<JobInfo> {
  const { intervalMs = 1200, timeoutMs = 15 * 60 * 1000, signal } = opts;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const job = await fetchJob(jobId, signal);
    if (job.status === "done" || job.status === "dead") return job;
    if (Date.now() >= deadline) throw new Error("后台任务超时，请稍后重试");
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export const fetchWikiPages = (
  space?: string,
  q?: string,
  page = 1,
  page_size = 20
) => {
  const params = new URLSearchParams();
  if (space) params.set("space", space);
  if (q) params.set("q", q);
  params.set("page", String(page));
  params.set("page_size", String(page_size));
  return request<Page<WikiPage>>(`/wiki/pages?${params.toString()}`);
};

export const fetchWikiPage = (id: string) =>
  request<WikiPageDetail>(`/wiki/pages/${id}`);

export const resolveWikiPage = (spaceId: string, slug: string) =>
  request<{ page_id: string; title: string }>(
    `/wiki/spaces/${spaceId}/resolve?slug=${encodeURIComponent(slug)}`
  );

export const resyncWikiPage = (pageId: string) =>
  request<WikiPageDetail>(`/wiki/pages/${pageId}/sync`, { method: "POST" });

export const fetchWikiGraph = (spaceId: string, tag?: string, limit?: number) => {
  const params = new URLSearchParams();
  if (tag) params.set("tag", tag);
  if (limit) params.set("limit", String(limit));
  const qs = params.toString();
  return request<WikiGraph>(
    `/wiki/graph?space=${encodeURIComponent(spaceId)}${qs ? `&${qs}` : ""}`
  );
};

// ---- 模型设置 ----
export const fetchLlmSettings = () => request<LLMSettings>("/settings/llm");

export interface LLMModels {
  models: string[];
  current: string;
  source: "user" | "env" | "none";
}

/** 按已配置的 API Key / Base URL 拉取可用模型（上游不支持时抛错，调用方回退当前模型）。 */
export const fetchLlmModels = () => request<LLMModels>("/settings/llm/models");

/** 用配置页中**尚未保存**的 Base URL / Key 拉取模型（不落库，Key 走请求体）。 */
export const fetchLlmModelsWithKey = (data: { base_url: string; api_key?: string }) =>
  request<LLMModels>("/settings/llm/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export interface LLMSettingsPayload {
  base_url: string;
  model: string;
  /** 留空不修改已存 Key；提供新值则覆盖 */
  api_key?: string;
  temperature: number;
  max_tokens: number;
}

export const saveLlmSettings = (data: LLMSettingsPayload) =>
  request<LLMSettings>("/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteLlmSettings = () =>
  request<{ ok: boolean; message: string }>("/settings/llm", { method: "DELETE" });

// ---- 管理后台（仅管理员；非管理员后端 403）----
export const fetchAdminOverview = () => request<AdminOverview>("/admin/overview");

export const fetchAdminUsage = (days = 7, userId?: string) => {
  const params = new URLSearchParams({ days: String(days) });
  if (userId) params.set("user_id", userId);
  return request<AdminUsagePoint[]>(`/admin/usage?${params.toString()}`);
};

export interface AdminUserQuery {
  q?: string;
  role?: string;
  status?: string;
  include_deleted?: boolean;
  page?: number;
  page_size?: number;
}

export const fetchAdminUsers = (query: AdminUserQuery = {}) => {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.role) params.set("role", query.role);
  if (query.status) params.set("status", query.status);
  if (query.include_deleted) params.set("include_deleted", "true");
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.page_size ?? 20));
  return request<Page<AdminUser>>(`/admin/users?${params.toString()}`);
};

export const fetchAdminUser = (id: string) =>
  request<AdminUserDetail>(`/admin/users/${id}`);

export const createAdminUser = (data: {
  username: string;
  password: string;
  role: string;
}) =>
  request<AdminUser>("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const updateAdminUser = (
  id: string,
  data: { role?: string; status?: string; password?: string }
) =>
  request<AdminUserDetail>(`/admin/users/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteAdminUser = (id: string, reason?: string) =>
  request<{ deleted: string; soft: boolean }>(`/admin/users/${id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });

export const restoreAdminUser = (id: string) =>
  request<{ id: string; soft: boolean; message: string }>(
    `/admin/users/${id}/restore`,
    { method: "POST" }
  );

export const forceLogoutAdminUser = (id: string) =>
  request<{ id: string; soft: boolean; message: string }>(
    `/admin/users/${id}/force-logout`,
    { method: "POST" }
  );

export const fetchAdminKnowledge = () =>
  request<AdminKnowledge>("/admin/knowledge");

export const fetchAdminAudit = (query: {
  action?: string;
  user_id?: string;
  request_id?: string;
  result?: string;
  page?: number;
  page_size?: number;
} = {}) => {
  const params = new URLSearchParams();
  if (query.action) params.set("action", query.action);
  if (query.user_id) params.set("user_id", query.user_id);
  if (query.request_id) params.set("request_id", query.request_id);
  if (query.result) params.set("result", query.result);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.page_size ?? 20));
  return request<Page<AdminAuditItem>>(`/admin/audit?${params.toString()}`);
};

export const fetchAdminEvalRuns = (query: {
  status?: string;
  source_scope?: string;
  page?: number;
  page_size?: number;
} = {}) => {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.source_scope) params.set("source_scope", query.source_scope);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.page_size ?? 20));
  return request<Page<AdminEvalRun>>(`/admin/eval/runs?${params.toString()}`);
};

export const createAdminEvalRun = (data: {
  source_scope?: string;
  trigger?: string;
} = {}) =>
  request<AdminEvalRun>("/admin/eval/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const testLlmSettings = (data: {
  base_url: string;
  model: string;
  api_key?: string;
}) =>
  request<{ ok: boolean; message: string; reply?: string }>("/settings/llm/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

// ---- Human-in-the-loop：确认/取消挂起的副作用操作 ----
export const confirmChat = (sessionId: string, approve: boolean) =>
  request<{ reply: string }>("/chat/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, approve }),
  });

// ---- SSE 流式对话 ----
export interface StreamHandlers {
  onSession: (sessionId: string) => void;
  onChunk: (text: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
  /** 挂起确认操作（human-in-the-loop） */
  onPending?: (actions: PendingAction[]) => void;
  /** 取消信号：调用方（停止生成按钮/会话切换）用它中断请求 */
  signal?: AbortSignal;
}

export async function streamChat(
  message: string,
  sessionId: string | null,
  handlers: StreamHandlers
): Promise<void> {
  // 与 request() 一致：携带认证令牌（此前遗漏导致流式对话 401 未登录）
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let resp: Response;
  try {
    resp = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ message, session_id: sessionId }),
      signal: handlers.signal,
    });
  } catch (err) {
    // 用户主动停止（AbortController）或网络层失败
    handlers.onError((err as Error)?.name === "AbortError" ? "已停止生成" : "网络连接失败，请重试");
    return;
  }
  if (resp.status === 401) {
    // 登录过期：清除令牌并通知应用回到登录页（与 request() 行为一致）
    clearToken();
    window.dispatchEvent(new Event("auth-expired"));
    handlers.onError("登录已过期，请重新登录");
    return;
  }
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
    if (!data) return; // SSE 注释（心跳 ": ping"）等无数据行直接跳过
    let payload: {
      session_id?: string;
      text?: string;
      detail?: string;
      actions?: PendingAction[];
    };
    try {
      payload = JSON.parse(data);
    } catch {
      return; // 畸形分片丢弃，不让单条坏数据杀死整个流
    }
    if (event === "session" && payload.session_id) handlers.onSession(payload.session_id);
    else if (event === "chunk" && typeof payload.text === "string") handlers.onChunk(payload.text);
    else if (event === "pending" && Array.isArray(payload.actions)) handlers.onPending?.(payload.actions);
    else if (event === "error") handlers.onError(payload.detail ?? "未知错误");
    else if (event === "done") handlers.onDone();
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) dispatch(part);
    }
    if (buffer.trim()) dispatch(buffer);
  } catch (err) {
    // 读取中断（含 AbortError）：有终态提示，不留挂死的 UI
    handlers.onError((err as Error)?.name === "AbortError" ? "已停止生成" : "连接中断，请重试");
  }
}

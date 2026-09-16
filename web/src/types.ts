export interface Session {
  id: string;
  title: string;
  message_count: number;
  updated_at?: string;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string;
  /** 工具审计 / 待确认操作（human-in-the-loop）等附加信息 */
  extra?: {
    pending_confirmation?: PendingAction[];
    tool_calls?: unknown[];
    citations?: Citation[];
    trajectory?: Trajectory;
  };
}

export interface Citation {
  index: number;
  chunk_id: string;
  document_id?: string;
  /** 带类型的展示标签（`Wiki / 空间 / 页面` 或 `文档 / 文件名 / 第 N 页`） */
  source: string;
  /** 旧数据无此字段 → 仅文本展示、不可跳转 */
  source_kind?: "wiki" | "document";
  /** 文档页码；Wiki/无页码为 null */
  page?: number | null;
  snippet?: string;
  /** `source_kind=wiki` 且解析成功时提供（前端跳转目标） */
  wiki?: { page_id: string; space_id: string; space_name: string; rel_path: string };
}

/** Agent 轨迹单步：路由 / 节点 / 工具 / 回复（与后端 step 词汇表一一对应）。 */
export interface TrajectoryStep {
  type: "route" | "node" | "tool" | "answer";
  /** type=route */
  route?: string;
  source?: "llm" | "keyword";
  /** type=node */
  node?: string;
  /** type=tool */
  name?: string;
  arguments?: string;
  result?: string;
  status?: "ok" | "pending_confirmation";
  /** type=answer */
  chars?: number;
  /** 该步耗时（毫秒；route/tool 有） */
  ms?: number;
}

/** 一次回答的完整轨迹（后端规范化后落 Message.extra.trajectory）。 */
export interface Trajectory {
  engine: string;
  total_ms: number;
  truncated: boolean;
  steps: TrajectoryStep[];
}

export interface PendingAction {
  name: string;
  arguments?: string;
  tool_call_id?: string;
}

export interface LLMSettings {
  base_url: string;
  model: string;
  temperature: number;
  max_tokens: number;
  api_key_set: boolean;
  api_key_preview: string;
  source: "user" | "env" | "none";
}

// ---- Wiki ----
export interface WikiSpace {
  id: string;
  name: string;
  source_type: string;
  page_count: number;
  last_synced_at?: string | null;
}

export interface WikiSyncStats {
  added: number;
  updated: number;
  moved: number;
  deleted: number;
  failed: number;
  total: number;
  skipped?: number;
  imported_files?: number | null;
}

/** J1：异步摄取/同步被受理（后端 202 + 作业 id，前端轮询 /jobs/{id}）。 */
export interface WikiSyncAccepted {
  job_id: string;
  status: string;
}

/** 同步类接口返回：内联统计 或 异步作业受理（开关决定）。 */
export type WikiSyncResponse = WikiSyncStats | WikiSyncAccepted;

/** 通用后台作业（GET /jobs/{id}）。 */
export interface JobInfo {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "dead";
  progress: number;
  attempts: number;
  max_attempts: number;
  error?: string | null;
  result: Record<string, unknown>;
  payload?: Record<string, unknown>;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WikiPage {
  id: string;
  space_id: string;
  space_name?: string | null;
  rel_path: string;
  title: string;
  slug: string;
  document_id?: string | null;
  page_type?: string;
}

export interface WikiLinkItem {
  target_slug: string;
  target_page_id?: string | null;
  alias?: string | null;
  kind: string;
}

export interface WikiBacklink {
  source_page_id: string;
  source_title?: string | null;
}

export interface WikiPageDetail extends WikiPage {
  content: string;
  tags: string[];
  links: WikiLinkItem[];
  backlinks: WikiBacklink[];
  document_status?: string | null;
}

export interface WikiGraphNode {
  id: string;
  title: string;
  slug: string;
  space_id: string;
  space?: string | null;
  degree: number;
  tags: string[];
}

export interface WikiGraphEdge {
  source: string;
  target: string;
  kind: string;
  relation?: string | null;
}

/** 知识图谱数据（节点=页面，边=已解析双链）。 */
export interface WikiGraph {
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
  total_nodes: number;
  truncated: boolean;
}

// ---- 回收站（软删除）----
export interface TrashItem {
  type: "todo" | "document" | "session" | "memory" | "wiki_page";
  id: string;
  label: string;
  deleted_at?: string | null;
}

export interface DocItem {
  id: string;
  title: string;
  source_type: string;
  status: string;
  chunk_count: number;
  created_at?: string;
}

export interface ChunkDetail {
  chunk_index: number;
  content: string;
  headings: string[];
  page?: number | null;
}

export interface DocDetail extends DocItem {
  error?: string | null;
  chunks: ChunkDetail[];
}

export interface SessionFile {
  id: string;
  filename: string;
  size: number;
  created_at?: string;
}

export interface Profile {
  id: string;
  username: string;
  role: string;
  created_at?: string;
  session_count: number;
  message_count: number;
  todo_count: number;
  doc_count: number;
  chunk_count: number;
}

export interface MemoryItem {
  id: string;
  fact: string;
  category: string;
  category_label: string;
  confidence: number;
  created_at?: string;
}

export interface TodoItem {
  id: string;
  title: string;
  status: string;
  priority: number;
  due_date?: string | null;
  category_id?: string | null;
  category_name?: string | null;
  category_color?: string | null;
  tags?: string[];
}

export interface Category {
  id: string;
  name: string;
  color: string;
}

// ---- 管理后台（ADMIN_PLAN）----
export interface AdminUser {
  id: string;
  username: string;
  role: "user" | "admin" | string;
  status: "active" | "disabled" | string;
  has_key: boolean;
  deleted_at?: string | null;
  created_at?: string | null;
}

export interface AdminUserDetail extends AdminUser {
  session_count: number;
  document_count: number;
  last_active?: string | null;
}

export interface AdminEvalRun {
  id: string;
  dataset_id?: string | null;
  status: "queued" | "running" | "done" | "failed" | string;
  trigger: string;
  source_scope: string;
  config_fingerprint: Record<string, unknown>;
  metrics: Record<string, number>;
  total: number;
  passed: number;
  progress: number;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
}

export interface AdminOverview {
  users_total: number;
  users_active: number;
  users_disabled: number;
  admins: number;
  requests_today: number;
  tokens_in_today: number;
  tokens_out_today: number;
  cost_today: number;
  error_rate_7d: number;
  latest_eval?: AdminEvalRun | null;
}

export interface AdminUsagePoint {
  day: string;
  requests: number;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  errors: number;
}

export interface AdminSourceStat {
  source_type: string;
  documents: number;
  chunks: number;
}

export interface AdminWikiSpaceStat {
  id: string;
  name: string;
  owner_id?: string | null;
  page_count: number;
  last_synced_at?: string | null;
}

export interface AdminKnowledge {
  documents_total: number;
  chunks_total: number;
  failed_documents: number;
  by_source: AdminSourceStat[];
  wiki_spaces: number;
  wiki_pages: number;
  wiki_dangling_links: number;
  spaces: AdminWikiSpaceStat[];
}

export interface AdminAuditItem {
  id: string;
  request_id?: string | null;
  user_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  result: string;
  meta: Record<string, unknown>;
  created_at?: string | null;
}

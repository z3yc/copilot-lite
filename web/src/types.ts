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
  };
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
  imported_files?: number | null;
}

export interface WikiPage {
  id: string;
  space_id: string;
  space_name?: string | null;
  rel_path: string;
  title: string;
  slug: string;
  document_id?: string | null;
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

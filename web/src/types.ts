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

export interface TodoItem {
  id: string;
  title: string;
  status: string;
  priority: number;
  due_date?: string;
}

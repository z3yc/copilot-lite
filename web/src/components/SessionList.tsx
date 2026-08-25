import { useEffect, useState } from "react";
import { deleteSession, fetchSessions } from "../api";
import type { Session } from "../types";

interface Props {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export default function SessionList({ activeId, onSelect, onNew }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      setSessions(await fetchSessions());
    } catch (err) {
      console.error("加载会话失败", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [activeId]);

  const remove = async (id: string) => {
    if (!confirm("删除该会话？历史消息将一并删除。")) return;
    try {
      await deleteSession(id);
      if (activeId === id) onNew();
      load();
    } catch (err) {
      alert(`删除失败: ${err}`);
    }
  };

  return (
    <aside className="sidebar">
      <button className="btn primary new-btn" onClick={onNew}>
        ＋ 新会话
      </button>

      <div className="session-list">
        {loading && <div className="dim">加载中…</div>}
        {!loading && sessions.length === 0 && (
          <div className="dim">暂无会话</div>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`session-item ${s.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(s.id)}
          >
            <div className="session-title">{s.title || "未命名会话"}</div>
            <div className="session-meta">
              {s.message_count} 条消息
              <span
                className="session-del"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(s.id);
                }}
                title="删除会话"
              >
                ✕
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="sidebar-footer dim">
        <a href="#kb" onClick={(e) => e.preventDefault()}>
          Copilot-Lite v0.1.0
        </a>
      </div>
    </aside>
  );
}

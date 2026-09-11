import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Empty, Input, List, Popconfirm, Skeleton, Typography } from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  MessageOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  deleteSession,
  exportSessionMarkdown,
  fetchSessions,
  renameSession,
} from "../api";
import type { Session } from "../types";

const { Text } = Typography;

interface Props {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export default function SessionList({ activeId, onSelect, onNew }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async (kw: string) => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await fetchSessions(kw.trim() || undefined));
    } catch (err) {
      console.error("加载会话失败", err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  // 会话切换立即重载；搜索输入防抖 300ms
  useEffect(() => {
    const timer = setTimeout(() => load(keyword), keyword.trim() ? 300 : 0);
    return () => clearTimeout(timer);
  }, [activeId, keyword, load]);

  const remove = async (id: string) => {
    try {
      await deleteSession(id);
      if (activeId === id) onNew();
      load(keyword);
    } catch (err) {
      console.error("删除失败", err);
    }
  };

  const startEdit = (s: Session) => {
    setEditingId(s.id);
    setDraft(s.title || "");
  };

  const saveEdit = async (s: Session) => {
    const title = draft.trim();
    setEditingId(null);
    if (!title || title === s.title) return;
    try {
      const updated = await renameSession(s.id, title);
      setSessions((prev) =>
        prev.map((x) => (x.id === s.id ? { ...x, title: updated.title } : x))
      );
    } catch (err) {
      console.error("重命名失败", err);
    }
  };

  const handleExport = async (s: Session) => {
    try {
      const text = await exportSessionMarkdown(s.id);
      const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${s.title || "session"}.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("导出失败", err);
    }
  };

  return (
    <div className="session-pane">
      <Button
        type="primary"
        block
        icon={<PlusOutlined />}
        onClick={onNew}
        style={{ marginBottom: 8 }}
      >
        新会话
      </Button>
      <Input.Search
        allowClear
        placeholder="搜索会话标题"
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        style={{ marginBottom: 10 }}
      />

      {loading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : error ? (
        <Alert
          type="error"
          showIcon
          title="加载会话失败"
          description={error}
          action={
            <Button size="small" onClick={() => load(keyword)}>
              重试
            </Button>
          }
        />
      ) : sessions.length === 0 ? (
        <Empty
          description={keyword ? "无匹配会话" : "暂无会话"}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <List
          className="session-list"
          dataSource={sessions}
          renderItem={(s) => (
            <List.Item
              className={`session-item ${s.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(s.id)}
              style={{ cursor: "pointer", padding: "10px 12px" }}
              actions={[
                <Button
                  key="export"
                  type="text"
                  size="small"
                  title="导出 Markdown"
                  icon={<DownloadOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleExport(s);
                  }}
                />,
                <Button
                  key="edit"
                  type="text"
                  size="small"
                  title="重命名"
                  icon={<EditOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    startEdit(s);
                  }}
                />,
                <Popconfirm
                  key="del"
                  title="删除该会话？可在回收站恢复"
                  onConfirm={(e) => {
                    e?.stopPropagation();
                    remove(s.id);
                  }}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    title="删除会话"
                    icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>,
              ]}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                {editingId === s.id ? (
                  <Input
                    size="small"
                    autoFocus
                    value={draft}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setDraft(e.target.value)}
                    onPressEnter={() => saveEdit(s)}
                    onBlur={() => saveEdit(s)}
                  />
                ) : (
                  <Text
                    strong={s.id === activeId}
                    ellipsis
                    style={{ display: "block", fontSize: 13 }}
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      startEdit(s);
                    }}
                  >
                    {s.title || "未命名会话"}
                  </Text>
                )}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <MessageOutlined /> {s.message_count} 条消息
                </Text>
              </div>
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

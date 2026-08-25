import { useEffect, useState } from "react";
import { Button, Empty, List, Popconfirm, Spin, Typography } from "antd";
import {
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { deleteSession, fetchSessions } from "../api";
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
    try {
      await deleteSession(id);
      if (activeId === id) onNew();
      load();
    } catch (err) {
      console.error("删除失败", err);
    }
  };

  return (
    <div className="session-pane">
      <Button
        type="primary"
        block
        icon={<PlusOutlined />}
        onClick={onNew}
        style={{ marginBottom: 10 }}
      >
        新会话
      </Button>

      {loading ? (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin size="small" />
        </div>
      ) : sessions.length === 0 ? (
        <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
                <Popconfirm
                  key="del"
                  title="删除该会话？"
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
                    icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>,
              ]}
            >
              <div style={{ minWidth: 0 }}>
                <Text
                  strong={s.id === activeId}
                  ellipsis
                  style={{ display: "block", fontSize: 13 }}
                >
                  {s.title || "未命名会话"}
                </Text>
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

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Empty, List, Spin, Tag, Typography, message } from "antd";
import { UndoOutlined } from "@ant-design/icons";
import { fetchTrash, restoreTrashItem } from "../api";
import type { TrashItem } from "../types";

const { Text } = Typography;

const TYPE_LABEL: Record<string, string> = {
  todo: "待办",
  document: "文档",
  session: "会话",
  memory: "记忆",
  wiki_page: "Wiki 页面",
};

/** 回收站：展示软删除数据并支持恢复（对应后端 /trash）。 */
export default function TrashPanel() {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setItems(await fetchTrash());
    } catch (err) {
      console.error("加载回收站失败", err);
      message.error("加载回收站失败，请重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const restore = async (item: TrashItem) => {
    try {
      await restoreTrashItem(item.type, item.id);
      message.success("已恢复");
      load();
    } catch (err) {
      message.error(`${err}`);
    }
  };

  if (loading) {
    return <Spin />;
  }

  return (
    <Card className="profile-card" title="🗑️ 回收站（删除的数据可恢复）">
      <div className="dim" style={{ marginBottom: 8, fontSize: 13 }}>
        删除只做标记、不物理删除；恢复后自动回到原位置。
      </div>
      {items.length === 0 ? (
        <Empty description="回收站为空" />
      ) : (
        <List
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  key="restore"
                  size="small"
                  icon={<UndoOutlined />}
                  onClick={() => restore(item)}
                >
                  恢复
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Text ellipsis style={{ maxWidth: 360 }}>
                    {item.label || item.id}
                  </Text>
                }
                description={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag>{TYPE_LABEL[item.type] ?? item.type}</Tag>
                    {item.deleted_at
                      ? new Date(item.deleted_at).toLocaleString("zh-CN")
                      : ""}
                  </Text>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

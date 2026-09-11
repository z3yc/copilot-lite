import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Modal,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  DeleteOutlined,
  InboxOutlined,
  LinkOutlined,
  PlusOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  createWikiSpace,
  deleteWikiSpace,
  fetchWikiPage,
  fetchWikiPages,
  fetchWikiSpaces,
  importWikiZip,
  syncWikiSpace,
} from "../api";
import type { WikiPage, WikiPageDetail, WikiSpace } from "../types";
import { renderMarkdown } from "../utils/markdown";

const { Text, Title } = Typography;
const { Dragger } = Upload;
const PAGE_SIZE = 20;

/** Wiki 管理：空间创建/删除、zip 导入、手动同步、页面浏览与双链面板。 */
export default function WikiPanel() {
  const [spaces, setSpaces] = useState<WikiSpace[]>([]);
  const [activeSpace, setActiveSpace] = useState<string | undefined>();
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [detail, setDetail] = useState<WikiPageDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");

  const loadSpaces = useCallback(async () => {
    try {
      const list = await fetchWikiSpaces();
      setSpaces(list);
      setActiveSpace((prev) => prev ?? list[0]?.id);
    } catch (err) {
      console.error("加载 Wiki 空间失败", err);
    }
  }, []);

  useEffect(() => {
    loadSpaces();
  }, [loadSpaces]);

  const loadPages = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWikiPages(
        activeSpace,
        keyword.trim() || undefined,
        page,
        PAGE_SIZE
      );
      setPages(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error("加载页面失败", err);
    } finally {
      setLoading(false);
    }
  }, [activeSpace, keyword, page]);

  useEffect(() => {
    loadPages();
  }, [loadPages]);

  const active = spaces.find((s) => s.id === activeSpace) ?? null;

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const space = await createWikiSpace(name);
      setSpaces((prev) => [...prev, space]);
      setActiveSpace(space.id);
      setNewName("");
      setCreateOpen(false);
      message.success("空间已创建，请导入 vault 的 zip 包");
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteWikiSpace(id);
      message.success("空间已删除");
      setDetail(null);
      setActiveSpace(undefined);
      await loadSpaces();
    } catch (err) {
      message.error(`${err}`);
    }
  };

  const handleSync = async () => {
    if (!activeSpace) return;
    setBusy(true);
    try {
      const stats = await syncWikiSpace(activeSpace);
      message.success(
        `同步完成：新增 ${stats.added} / 更新 ${stats.updated} / 移动 ${stats.moved} / 删除 ${stats.deleted}`
      );
      await Promise.all([loadSpaces(), loadPages()]);
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async (file: File) => {
    if (!activeSpace) {
      message.warning("请先选择或创建空间");
      return false;
    }
    setBusy(true);
    try {
      const stats = await importWikiZip(activeSpace, file);
      message.success(
        `已导入 ${stats.imported_files ?? 0} 个文件，新增 ${stats.added} 页`
      );
      await Promise.all([loadSpaces(), loadPages()]);
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setBusy(false);
    }
    return false;
  };

  const openPage = async (id: string) => {
    try {
      setDetail(await fetchWikiPage(id));
    } catch (err) {
      message.error(`${err}`);
    }
  };

  return (
    <div className="wiki-panel" style={{ flex: 1, display: "flex", overflow: "hidden" }}>
      <div
        style={{
          width: 340,
          minWidth: 300,
          borderRight: "1px solid var(--border)",
          padding: 12,
          overflow: "auto",
        }}
      >
        <Space direction="vertical" style={{ width: "100%" }} size={10}>
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Text strong>🕸️ Wiki 空间</Text>
            <Button size="small" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建
            </Button>
          </Space>

          <Select
            style={{ width: "100%" }}
            placeholder="选择空间"
            value={activeSpace}
            onChange={(v) => {
              setActiveSpace(v);
              setPage(1);
              setDetail(null);
            }}
            options={spaces.map((s) => ({ value: s.id, label: `${s.name}（${s.page_count} 页）` }))}
          />

          <Space>
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={busy}
              disabled={!activeSpace}
              onClick={handleSync}
            >
              同步
            </Button>
            {active && (
              <Popconfirm
                title="删除该空间？将清理页面/分块/向量"
                onConfirm={() => handleDelete(active.id)}
              >
                <Button size="small" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>

          <Input.Search
            allowClear
            placeholder="搜索页面标题"
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
          />

          {active && (
            <Dragger
              accept=".zip"
              showUploadList={false}
              beforeUpload={(file) => {
                handleImport(file as unknown as File);
                return false;
              }}
              style={{ padding: 8 }}
            >
              <p style={{ margin: 0 }}>
                <InboxOutlined />
              </p>
              <p className="dim" style={{ fontSize: 12, margin: 0 }}>
                上传 Obsidian vault 的 zip 包
              </p>
            </Dragger>
          )}

          <Card size="small" title="页面">
            {loading ? (
              <Spin size="small" />
            ) : pages.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无页面，请先导入" />
            ) : (
              <>
                <List
                  size="small"
                  dataSource={pages}
                  renderItem={(p) => (
                    <List.Item
                      style={{ cursor: "pointer", padding: "6px 4px" }}
                      onClick={() => openPage(p.id)}
                    >
                      <Text ellipsis style={{ fontSize: 13 }}>
                        {p.title}
                      </Text>
                    </List.Item>
                  )}
                />
                {total > PAGE_SIZE && (
                  <Pagination
                    size="small"
                    current={page}
                    pageSize={PAGE_SIZE}
                    total={total}
                    onChange={setPage}
                  />
                )}
              </>
            )}
          </Card>
        </Space>
      </div>

      <div style={{ flex: 1, padding: 16, overflow: "auto" }}>
        {!detail ? (
          <Empty description="从左侧选择一个 Wiki 页面查看内容与双链" />
        ) : (
          <>
            <Title level={4} style={{ marginTop: 0, marginBottom: 6 }}>
              {detail.title}
            </Title>
            <Space size={6} wrap style={{ marginBottom: 8 }}>
              {detail.tags.map((t) => (
                <Tag key={t} color="geekblue">
                  #{t}
                </Tag>
              ))}
              <Text type="secondary" style={{ fontSize: 12 }}>
                {detail.rel_path}
              </Text>
            </Space>
            <div
              className="wiki-content"
              // 消毒后渲染（唯一入口 utils/markdown）
              dangerouslySetInnerHTML={{ __html: renderMarkdown(detail.content) }}
            />

            <Card
              size="small"
              title={`反向链接（${detail.backlinks.length}）`}
              style={{ marginTop: 12 }}
            >
              {detail.backlinks.length === 0 ? (
                <Text type="secondary">暂无其他页面引用本页</Text>
              ) : (
                <Space direction="vertical">
                  {detail.backlinks.map((b) => (
                    <a key={b.source_page_id} onClick={() => openPage(b.source_page_id)}>
                      <LinkOutlined /> {b.source_title ?? b.source_page_id}
                    </a>
                  ))}
                </Space>
              )}
            </Card>

            <Card size="small" title={`出链（${detail.links.length}）`} style={{ marginTop: 12 }}>
              {detail.links.length === 0 ? (
                <Text type="secondary">本页未引用其他页面</Text>
              ) : (
                <Space direction="vertical">
                  {detail.links.map((l, i) => (
                    <span key={`${l.target_slug}-${i}`}>
                      {l.kind === "embed" ? "!" : ""}
                      {l.target_page_id ? (
                        <a onClick={() => openPage(l.target_page_id as string)}>
                          {l.alias || l.target_slug}
                        </a>
                      ) : (
                        <Text type="secondary">{l.target_slug}（悬空）</Text>
                      )}
                    </span>
                  ))}
                </Space>
              )}
            </Card>
          </>
        )}
      </div>

      <Modal
        title="新建 Wiki 空间"
        open={createOpen}
        onOk={handleCreate}
        confirmLoading={busy}
        onCancel={() => setCreateOpen(false)}
      >
        <Input
          placeholder="空间名称（如 my-vault）"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onPressEnter={handleCreate}
        />
      </Modal>
    </div>
  );
}

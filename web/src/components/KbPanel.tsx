import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  Popconfirm,
  Skeleton,
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
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { deleteDoc, fetchDocDetail, fetchDocs, retryDoc, uploadDocs } from "../api";
import type { DocDetail, DocItem } from "../types";

const { Text, Paragraph } = Typography;
const { Dragger } = Upload;
const { Search } = Input;

const SOURCE_META: Record<string, { label: string; icon: string }> = {
  md: { label: "笔记", icon: "📄" },
  wiki: { label: "Wiki", icon: "🕸️" },
  pdf: { label: "PDF", icon: "📕" },
  docx: { label: "Word", icon: "📘" },
  code: { label: "代码", icon: "💻" },
  web: { label: "网页", icon: "🌐" },
};

const ACCEPT =
  ".md,.txt,.pdf,.docx,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.sql,.html,.htm";

function StatusTag({ status }: { status: string }) {
  if (status === "ready") return <Tag color="success">已就绪</Tag>;
  if (status === "parsing") return <Tag color="processing">摄取中</Tag>;
  return <Tag color="error">失败</Tag>;
}

interface Props {
  activeCat: string;
  onCatChange: (cat: string) => void;
}

export default function KbPanel({ activeCat, onCatChange }: Props) {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [search, setSearch] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // 加载（分类 + 内容级搜索，300ms 防抖）
  const loadDocs = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const kw = search.trim();
      const type = activeCat !== "all" ? activeCat : undefined;
      setDocs(await fetchDocs(kw || undefined, type));
    } catch (err) {
      console.error("加载知识库失败", err);
    } finally {
      setLoadingDocs(false);
    }
  }, [search, activeCat]);

  useEffect(() => {
    const timer = setTimeout(loadDocs, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [loadDocs, search]);

  const toggleDetail = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setLoadingDetail(true);
    try {
      setDetail(await fetchDocDetail(id));
    } catch (err) {
      message.error(`加载详情失败: ${err}`);
    } finally {
      setLoadingDetail(false);
    }
  };

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const results = await uploadDocs(Array.from(files));
      message.success(`上传成功 ${results.length} 个文档`);
      setSearch("");
      loadDocs();
    } catch (err) {
      message.error(`上传失败: ${err}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteDoc(id);
      if (expandedId === id) {
        setExpandedId(null);
        setDetail(null);
      }
      message.success("已删除");
      fetchDocs(search.trim() || undefined).then(setDocs).catch(() => {});
    } catch (err) {
      message.error(`删除失败: ${err}`);
    }
  };

  const retry = async (id: string) => {
    try {
      await retryDoc(id);
      message.success("已重新摄取");
      loadDocs();
    } catch (err) {
      message.error(`重试失败: ${err}`);
    }
  };

  // 按类型分组展示（搜索/分类已由后端 + 侧边栏过滤，这里仅分组）
  const groups = useMemo(() => {
    const g = new Map<string, DocItem[]>();
    docs.forEach((d) => {
      const meta = SOURCE_META[d.source_type] ?? { label: "其他", icon: "📄" };
      const key = `${meta.icon} ${meta.label}`;
      if (!g.has(key)) g.set(key, []);
      g.get(key)!.push(d);
    });
    return Array.from(g.entries());
  }, [docs]);

  const hasOtherCats = docs.some((d) => d.source_type !== activeCat);

  return (
    <div className="kb-panel">
      <div className="kb-toolbar">
        <Space>
          <Text strong style={{ fontSize: 16 }}>
            📚 知识库管理
          </Text>
          <Button size="small" icon={<ReloadOutlined />} onClick={loadDocs} />
        </Space>
        <Space>
          <Search
            placeholder="搜索标题或文档内容"
            allowClear
            prefix={<SearchOutlined />}
            style={{ width: 220 }}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Button
            type="primary"
            icon={<InboxOutlined />}
            onClick={() => fileRef.current?.click()}
            loading={uploading}
          >
            {uploading ? "上传中…" : "上传文档"}
          </Button>
          <input
            ref={fileRef}
            type="file"
            multiple
            hidden
            accept={ACCEPT}
            onChange={(e) => onUpload(e.target.files)}
          />
        </Space>
      </div>

      <div className="kb-body">
        {/* 当前分类提示（点击可清除分类回到全部） */}
        {activeCat !== "all" && (
          <div className="kb-cat-hint">
            当前筛选：
            <Tag
              closable
              color="geekblue"
              onClose={() => onCatChange("all")}
            >
              {SOURCE_META[activeCat]?.icon} {SOURCE_META[activeCat]?.label}
            </Tag>
            {hasOtherCats && (
              <Button type="link" size="small" onClick={() => onCatChange("all")}>
                查看全部
              </Button>
            )}
          </div>
        )}

        {loadingDocs && docs.length === 0 ? (
          <Skeleton active paragraph={{ rows: 5 }} />
        ) : docs.length === 0 ? (
          search ? (
            <Empty description="没有匹配的文档，换个关键词试试" />
          ) : (
            <Empty description="知识库为空，点击右上角上传文档">
              <Upload
                multiple
                accept={ACCEPT}
                showUploadList={false}
                beforeUpload={(file) => {
                  onUpload([file] as unknown as FileList);
                  return false;
                }}
              >
                <Dragger style={{ padding: 24 }}>
                  <p style={{ fontSize: 40, margin: 0 }}>📥</p>
                  <Text>点击或拖拽文档到此处上传</Text>
                  <div className="dim" style={{ fontSize: 12 }}>
                    支持 Markdown / PDF / Word / 代码 / 网页
                  </div>
                </Dragger>
              </Upload>
            </Empty>
          )
        ) : (
          <div className="kb-list">
            {groups.map(([groupName, items]) => (
              <div key={groupName} className="kb-group">
                <div className="kb-group-title">
                  {groupName}
                  <span className="dim">（{items.length} 个文档）</span>
                </div>
                {items.map((d) => {
                  const meta = SOURCE_META[d.source_type] ?? { label: "其他", icon: "📄" };
                  return (
                    <Card
                      key={d.id}
                      size="small"
                      className="doc-card"
                      onClick={() => toggleDetail(d.id)}
                      hoverable
                      title={
                        <Space>
                          <span style={{ fontSize: 16 }}>{meta.icon}</span>
                          <Text strong ellipsis style={{ maxWidth: 320 }}>
                            {d.title}
                          </Text>
                        </Space>
                      }
                      extra={
                        <Space size={8}>
                          <StatusTag status={d.status} />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {d.chunk_count} 分块
                          </Text>
                          {d.status === "failed" && (
                            <Button
                              type="text"
                              size="small"
                              title="重试摄取"
                              icon={<ReloadOutlined />}
                              onClick={(e) => {
                                e.stopPropagation();
                                retry(d.id);
                              }}
                            />
                          )}
                          <Popconfirm
                            title="删除该文档？其分块与向量将一并清理。"
                            onConfirm={() => remove(d.id)}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Popconfirm>
                        </Space>
                      }
                    >
                      {expandedId === d.id && (
                        <div onClick={(e) => e.stopPropagation()}>
                          {loadingDetail && <Spin size="small" />}
                          {detail && (
                            <>
                              {detail.error && (
                                <Text type="danger">⚠️ 摄取失败：{detail.error}</Text>
                              )}
                              <Collapse
                                size="small"
                                items={detail.chunks.map((c) => ({
                                  key: c.chunk_index,
                                  label: (
                                    <Space size={8}>
                                      <Tag color="geekblue">#{c.chunk_index}</Tag>
                                      {c.headings.length > 0 && (
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                          📁 {c.headings.join(" > ")}
                                        </Text>
                                      )}
                                      {c.page != null && (
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                          📄 第{c.page}页
                                        </Text>
                                      )}
                                    </Space>
                                  ),
                                  children: (
                                    <Paragraph
                                      style={{
                                        fontSize: 13,
                                        margin: 0,
                                        whiteSpace: "pre-wrap",
                                      }}
                                    >
                                      {c.content}
                                    </Paragraph>
                                  ),
                                }))}
                              />
                            </>
                          )}
                        </div>
                      )}
                    </Card>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

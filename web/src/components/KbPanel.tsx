import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
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
  BookOutlined,
  DeleteOutlined,
  FileTextOutlined,
  FolderOutlined,
  InboxOutlined,
  ReloadOutlined,
  SearchOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { deleteDoc, fetchDocDetail, fetchDocs, retryDoc, uploadDocs } from "../api";
import { ACCEPT_EXTENSIONS, SOURCE_META, sourceMeta } from "../constants";
import type { DocDetail, DocItem } from "../types";
import { keyboardActivate } from "../utils/a11y";

const { Text, Paragraph } = Typography;
const { Dragger } = Upload;
const { Search } = Input;

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
  const [errorDocs, setErrorDocs] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // 加载（分类 + 内容级搜索，300ms 防抖）
  const loadDocs = useCallback(async () => {
    setLoadingDocs(true);
    setErrorDocs(null);
    try {
      const kw = search.trim();
      const type = activeCat !== "all" ? activeCat : undefined;
      setDocs(await fetchDocs(kw || undefined, type));
    } catch (err) {
      console.error("加载知识库失败", err);
      setErrorDocs(err instanceof Error ? err.message : String(err));
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
      // 走统一的 loadDocs，保留当前分类 + 关键词筛选（此前漏传 activeCat 导致筛选丢失）
      loadDocs();
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
      const key = SOURCE_META[d.source_type] ? d.source_type : "other";
      if (!g.has(key)) g.set(key, []);
      g.get(key)!.push(d);
    });
    return Array.from(g.entries());
  }, [docs]);

  const hasOtherCats = docs.some((d) => d.source_type !== activeCat);
  const catMeta = sourceMeta(activeCat);

  return (
    <div className="kb-panel">
      <div className="kb-toolbar">
        <Space>
          <Text strong style={{ fontSize: 16 }}>
            <BookOutlined /> 知识库管理
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
            accept={ACCEPT_EXTENSIONS}
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
              <catMeta.Icon /> {catMeta.label}
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
        ) : errorDocs ? (
          <Alert
            type="error"
            showIcon
            title="加载知识库失败"
            description={errorDocs}
            action={
              <Button size="small" onClick={loadDocs}>
                重试
              </Button>
            }
          />
        ) : docs.length === 0 ? (
          search ? (
            <Empty description="没有匹配的文档，换个关键词试试" />
          ) : (
            <Empty description="知识库为空，点击右上角上传文档">
              <Upload
                multiple
                accept={ACCEPT_EXTENSIONS}
                showUploadList={false}
                beforeUpload={(file) => {
                  onUpload([file] as unknown as FileList);
                  return false;
                }}
              >
                <Dragger style={{ padding: 24 }}>
                  <p style={{ margin: 0 }}>
                    <InboxOutlined
                      style={{ fontSize: 40, color: "var(--color-primary)" }}
                    />
                  </p>
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
            {groups.map(([groupType, items]) => {
              const groupMeta = sourceMeta(groupType);
              return (
              <div key={groupType} className="kb-group">
                <div className="kb-group-title">
                  <groupMeta.Icon /> {groupMeta.label}
                  <span className="dim">（{items.length} 个文档）</span>
                </div>
                {items.map((d) => {
                  const meta = sourceMeta(d.source_type);
                  return (
                    <Card
                      key={d.id}
                      size="small"
                      className="doc-card"
                      role="button"
                      tabIndex={0}
                      aria-label={`查看文档：${d.title}`}
                      onClick={() => toggleDetail(d.id)}
                      onKeyDown={keyboardActivate(() => toggleDetail(d.id))}
                      hoverable
                      title={
                        <Space>
                          <meta.Icon style={{ fontSize: 16 }} />
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
                              aria-label="重试摄取"
                              icon={<ReloadOutlined />}
                              onClick={(e) => {
                                e.stopPropagation();
                                retry(d.id);
                              }}
                            />
                          )}
                          <Popconfirm
                            title="删除该文档？可在回收站恢复（索引停用，不物理删）"
                            onConfirm={() => remove(d.id)}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              aria-label="删除文档"
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
                                <Text type="danger">
                                  <WarningOutlined /> 摄取失败：{detail.error}
                                </Text>
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
                                          <FolderOutlined /> {c.headings.join(" > ")}
                                        </Text>
                                      )}
                                      {c.page != null && (
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                          <FileTextOutlined /> 第{c.page}页
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
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

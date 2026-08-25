import { useEffect, useRef, useState } from "react";
import { deleteDoc, fetchDocDetail, fetchDocs, uploadDocs } from "../api";
import type { DocDetail, DocItem } from "../types";

const SOURCE_LABEL: Record<string, string> = {
  md: "📄 笔记",
  pdf: "📕 PDF",
  docx: "📘 Word",
  code: "💻 代码",
  web: "🌐 网页",
};

export default function KbPanel() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      setDocs(await fetchDocs());
    } catch (err) {
      console.error("加载知识库失败", err);
    }
  };

  useEffect(() => {
    load();
  }, []);

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
      alert(`加载详情失败: ${err}`);
    } finally {
      setLoadingDetail(false);
    }
  };

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      await uploadDocs(Array.from(files));
      await load();
    } catch (err) {
      alert(`上传失败: ${err}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (id: string) => {
    if (!confirm("删除该文档？其分块与向量将一并清理。")) return;
    try {
      await deleteDoc(id);
      if (expandedId === id) {
        setExpandedId(null);
        setDetail(null);
      }
      load();
    } catch (err) {
      alert(`删除失败: ${err}`);
    }
  };

  return (
    <div className="kb-panel">
      <header className="chat-header">
        <span className="brand">📚 知识库</span>
        <button
          className="btn ghost"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? "上传中…" : "⬆ 上传文档"}
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          accept=".md,.txt,.pdf,.docx,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.sql,.html,.htm"
          onChange={(e) => onUpload(e.target.files)}
        />
      </header>

      <div className="kb-list">
        {docs.length === 0 && (
          <div className="dim empty">知识库为空，点击右上角上传文档</div>
        )}
        {docs.map((d) => (
          <div key={d.id} className="doc-card">
            <div className="doc-item" onClick={() => toggleDetail(d.id)}>
              <div className="doc-icon">{SOURCE_LABEL[d.source_type] ?? "📄"}</div>
              <div className="doc-info">
                <div className="doc-title">{d.title}</div>
                <div className="doc-meta">
                  {d.chunk_count} 个分块 ·{" "}
                  {d.status === "ready" ? (
                    <span className="ok">✅ 已就绪</span>
                  ) : d.status === "parsing" ? (
                    <span className="busy">⏳ 摄取中</span>
                  ) : (
                    <span className="err">❌ 失败</span>
                  )}
                  <span className="expand-hint">
                    {expandedId === d.id ? "▲ 收起" : "▼ 详情"}
                  </span>
                </div>
              </div>
              <button
                className="doc-del"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(d.id);
                }}
                title="删除"
              >
                ✕
              </button>
            </div>

            {expandedId === d.id && (
              <div className="doc-detail">
                {loadingDetail && <div className="dim">加载中…</div>}
                {detail && (
                  <>
                    {detail.error && (
                      <div className="detail-error">⚠️ 摄取失败：{detail.error}</div>
                    )}
                    <div className="detail-summary dim">
                      共 {detail.chunks.length} 个分块，点击可复制内容
                    </div>
                    {detail.chunks.length === 0 && (
                      <div className="dim">该文档暂无分块内容。</div>
                    )}
                    {detail.chunks.map((c) => (
                      <div key={c.chunk_index} className="chunk-card">
                        <div className="chunk-head">
                          <span className="chunk-idx">#{c.chunk_index}</span>
                          {c.headings.length > 0 && (
                            <span className="chunk-path">
                              📁 {c.headings.join(" > ")}
                            </span>
                          )}
                          {c.page != null && <span className="chunk-page">📄 第{c.page}页</span>}
                        </div>
                        <div className="chunk-content">{c.content}</div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { deleteDoc, fetchDocs, uploadDocs } from "../api";
import type { DocItem } from "../types";

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
        {docs.length === 0 && <div className="dim empty">知识库为空，点击右上角上传文档</div>}
        {docs.map((d) => (
          <div key={d.id} className="doc-item">
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
              </div>
            </div>
            <button className="doc-del" onClick={() => remove(d.id)} title="删除">
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

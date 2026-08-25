import { useEffect, useMemo, useState } from "react";
import { Badge, List, Spin, Typography } from "antd";
import { fetchDocs } from "../api";
import type { DocItem } from "../types";

const { Text } = Typography;

const SOURCE_META: Record<string, { label: string; icon: string }> = {
  md: { label: "笔记", icon: "📄" },
  pdf: { label: "PDF", icon: "📕" },
  docx: { label: "Word", icon: "📘" },
  code: { label: "代码", icon: "💻" },
  web: { label: "网页", icon: "🌐" },
};

interface Props {
  activeCat: string;
  onChange: (cat: string) => void;
  onRefresh?: () => void;
}

export default function DocCategoryNav({ activeCat, onChange }: Props) {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDocs()
      .then(setDocs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeCat]);

  const catCount = useMemo(() => {
    const map = new Map<string, number>();
    docs.forEach((d) => map.set(d.source_type, (map.get(d.source_type) ?? 0) + 1));
    return map;
  }, [docs]);

  const cats = useMemo(() => {
    const items: { key: string; label: string; icon: string; count: number }[] = [
      { key: "all", label: "全部", icon: "🗂️", count: docs.length },
    ];
    Object.entries(SOURCE_META).forEach(([key, meta]) => {
      const n = catCount.get(key) ?? 0;
      items.push({ key, label: meta.label, icon: meta.icon, count: n });
    });
    return items;
  }, [docs.length, catCount]);

  return (
    <div className="session-pane">
      {loading ? (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin size="small" />
        </div>
      ) : (
        <List
          size="small"
          dataSource={cats}
          renderItem={(c) => (
            <List.Item
              className={`cat-item ${activeCat === c.key ? "active" : ""}`}
              onClick={() => onChange(c.key)}
              style={{ cursor: "pointer", borderRadius: 8, padding: "8px 12px" }}
            >
              <Text>
                {c.icon} {c.label}
              </Text>
              <Badge count={c.count} showZero color={activeCat === c.key ? "#4f6ef7" : "#d9d9d9"} />
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

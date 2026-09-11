import { useEffect, useMemo, useState } from "react";
import { Badge, List, Spin, Typography, message } from "antd";
import { fetchDocs } from "../api";
import { ALL_SOURCE_META, SOURCE_META, type SourceMeta } from "../constants";
import type { DocItem } from "../types";
import { keyboardActivate } from "../utils/a11y";

const { Text } = Typography;

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
      .catch((err) => {
        console.error("加载分类失败", err);
        message.error("加载分类失败，请重试");
      })
      .finally(() => setLoading(false));
  }, [activeCat]);

  const catCount = useMemo(() => {
    const map = new Map<string, number>();
    docs.forEach((d) => map.set(d.source_type, (map.get(d.source_type) ?? 0) + 1));
    return map;
  }, [docs]);

  const cats = useMemo(() => {
    const items: { key: string; label: string; Icon: SourceMeta["Icon"]; count: number }[] = [
      {
        key: "all",
        label: ALL_SOURCE_META.label,
        Icon: ALL_SOURCE_META.Icon,
        count: docs.length,
      },
    ];
    Object.entries(SOURCE_META).forEach(([key, meta]) => {
      items.push({ key, label: meta.label, Icon: meta.Icon, count: catCount.get(key) ?? 0 });
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
              role="button"
              tabIndex={0}
              aria-label={`按分类筛选：${c.label}`}
              onClick={() => onChange(c.key)}
              onKeyDown={keyboardActivate(() => onChange(c.key))}
              style={{ cursor: "pointer", borderRadius: 8, padding: "8px 12px" }}
            >
              <Text>
                <c.Icon /> {c.label}
              </Text>
              <Badge
                count={c.count}
                showZero
                color={activeCat === c.key ? "var(--color-primary)" : "var(--color-neutral)"}
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

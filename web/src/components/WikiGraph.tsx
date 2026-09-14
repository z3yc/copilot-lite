import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Empty, Select, Space, Spin, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import ForceGraph2D from "react-force-graph-2d";

import { fetchWikiGraph } from "../api";
import type { WikiGraph, WikiGraphNode } from "../types";

const { Text } = Typography;

interface Props {
  spaceId?: string;
  spaceName?: string;
  /** 点击节点：打开对应 Wiki 页面。 */
  onOpenPage: (pageId: string) => void;
}

/** 知识图谱：2D 力导向（react-force-graph-2d），支持按标签过滤与节点截断提示。 */
export default function WikiGraphView({ spaceId, spaceName, onOpenPage }: Props) {
  const [data, setData] = useState<WikiGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tag, setTag] = useState<string | undefined>();
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [size, setSize] = useState({ width: 800, height: 520 });
  const containerRef = useRef<HTMLDivElement>(null);

  // 切换空间：清空上一次的标签候选
  useEffect(() => {
    setTag(undefined);
    setTagOptions([]);
  }, [spaceId]);

  useEffect(() => {
    if (!spaceId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchWikiGraph(spaceId, tag)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        // 累积标签候选（首屏未过滤时包含全部标签）
        setTagOptions((prev) =>
          Array.from(new Set([...prev, ...res.nodes.flatMap((n) => n.tags)])).sort()
        );
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [spaceId, tag, reloadKey]);

  // 容器尺寸自适应（力导向画布需要显式宽高）
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () =>
      setSize({
        width: el.clientWidth || 800,
        height: el.clientHeight || 520,
      });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const graphData = useMemo(
    () => ({
      nodes: data?.nodes ?? [],
      links: data?.edges ?? [],
    }),
    [data]
  );

  const nodeColor = (node: WikiGraphNode) =>
    node.tags[0] ? tagColor(node.tags[0]) : "#5b8ff9";

  return (
    <div className="wiki-graph">
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Text strong>{spaceName ? `${spaceName} · 知识图谱` : "知识图谱"}</Text>
        <Space size={8}>
          <Select
            allowClear
            showSearch
            size="small"
            placeholder="按标签过滤"
            style={{ minWidth: 160 }}
            value={tag}
            onChange={(value) => setTag(value)}
            options={tagOptions.map((t) => ({ value: t, label: `#${t}` }))}
          />
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => setReloadKey((k) => k + 1)}
          >
            刷新
          </Button>
        </Space>
      </Space>

      {data?.truncated && (
        <Alert
          type="info"
          showIcon
          style={{ margin: "8px 0" }}
          message={`节点较多，仅展示关联度最高的 ${data.nodes.length} / ${data.total_nodes} 个节点；可按标签筛选或缩小空间。`}
        />
      )}

      <div className="wiki-graph-canvas" ref={containerRef}>
        {loading ? (
          <div className="wiki-graph-state">
            <Spin />
          </div>
        ) : error ? (
          <div className="wiki-graph-state">
            <Alert
              type="error"
              showIcon
              message="加载图谱失败"
              description={error}
              action={
                <Button size="small" onClick={() => setReloadKey((k) => k + 1)}>
                  重试
                </Button>
              }
            />
          </div>
        ) : graphData.nodes.length === 0 ? (
          <div className="wiki-graph-state">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={tag ? `没有带 #${tag} 标签的页面` : "暂无页面，请先导入 vault"}
            />
          </div>
        ) : (
          <ForceGraph2D
            graphData={graphData}
            nodeId="id"
            nodeLabel={(n) => `${n.title ?? ""}（关联 ${n.degree ?? 0}）`}
            nodeVal={(n) => Number(n.degree ?? 0) + 1}
            nodeColor={(n) => nodeColor(n as unknown as WikiGraphNode)}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkColor={() => "#bfbfbf"}
            onNodeClick={(n) => onOpenPage(String(n.id))}
            width={size.width}
            height={size.height}
          />
        )}
      </div>
    </div>
  );
}

/** 按标签名生成稳定颜色（简单哈希 → HSL）。 */
function tagColor(tag: string): string {
  let hash = 0;
  for (let i = 0; i < tag.length; i += 1) {
    hash = (hash * 31 + tag.charCodeAt(i)) % 360;
  }
  return `hsl(${hash}, 65%, 55%)`;
}

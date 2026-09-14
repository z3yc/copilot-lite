/**
 * 管理后台（ADMIN_PLAN §9 N1.8）：概览 / 用户与用量 / 知识库 / 审计日志 / 质量看板。
 *
 * 仅管理员入口可见（App 按 role 渲染），后端另有 require_admin 强制鉴权。
 * 图表用 recharts（体积小）；管理接口默认只回元数据，不含对话原文/密钥。
 */

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
  type TableColumnsType,
} from "antd";
import {
  ArrowLeftOutlined,
  BookOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SafetyOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

import AdminUsers from "./AdminUsers";
import {
  createAdminEvalRun,
  fetchAdminAudit,
  fetchAdminEvalRuns,
  fetchAdminKnowledge,
  fetchAdminOverview,
  fetchAdminUsage,
} from "../api";
import type {
  AdminAuditItem,
  AdminEvalRun,
  AdminKnowledge,
  AdminOverview,
  AdminUsagePoint,
} from "../types";

const { Title, Text } = Typography;

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  queued: { color: "default", label: "排队中" },
  running: { color: "processing", label: "运行中" },
  done: { color: "success", label: "完成" },
  failed: { color: "error", label: "失败" },
};

const RESULT_TAG: Record<string, string> = { ok: "green", denied: "orange", error: "red" };

const SCOPE_LABEL: Record<string, string> = { all: "全部", docs: "文档", wiki: "Wiki" };

// ---------------- 概览 ----------------

function OverviewTab() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [usage, setUsage] = useState<AdminUsagePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [o, u] = await Promise.all([fetchAdminOverview(), fetchAdminUsage(7)]);
      setOverview(o);
      setUsage(u);
    } catch (err) {
      setError((err as Error).message || "加载概览失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <Alert type="error" showIcon message={error} />;
  if (!overview) return <Card loading={loading} />;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[12, 12]}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="用户总数" value={overview.users_total} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="管理员" value={overview.admins} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="今日请求" value={overview.requests_today} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="今日 Token 入/出" value={`${overview.tokens_in_today}/${overview.tokens_out_today}`} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="今日成本" precision={4} value={overview.cost_today} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="近 7 日错误率"
              precision={2}
              suffix="%"
              value={overview.error_rate_7d * 100}
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title="近 7 日用量趋势"
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void load()} />}
      >
        {usage.length === 0 ? (
          <Empty description="暂无用量数据" />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={usage}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" fontSize={12} />
                <YAxis fontSize={12} />
                <RTooltip />
                <Legend />
                <Bar dataKey="requests" name="请求数" fill="var(--color-primary)" />
                <Bar dataKey="errors" name="错误数" fill="#ff7875" />
              </BarChart>
            </ResponsiveContainer>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={usage}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" fontSize={12} />
                <YAxis fontSize={12} />
                <RTooltip />
                <Legend />
                <Line dataKey="tokens_in" name="Token 入" stroke="#4f6ef7" dot={false} />
                <Line dataKey="tokens_out" name="Token 出" stroke="#52c41a" dot={false} />
                <Line dataKey="cost" name="成本" stroke="#faad14" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>

      <Card size="small" title="最新评测">
        {overview.latest_eval ? (
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="状态">
              <Tag color={STATUS_TAG[overview.latest_eval.status]?.color}>
                {STATUS_TAG[overview.latest_eval.status]?.label ?? overview.latest_eval.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              {SCOPE_LABEL[overview.latest_eval.source_scope] ?? overview.latest_eval.source_scope}
            </Descriptions.Item>
            <Descriptions.Item label="通过/总数">
              {overview.latest_eval.passed}/{overview.latest_eval.total}
            </Descriptions.Item>
            <Descriptions.Item label="时间">
              {overview.latest_eval.created_at
                ? dayjs(overview.latest_eval.created_at).format("YYYY-MM-DD HH:mm")
                : "-"}
            </Descriptions.Item>
            {Object.entries(overview.latest_eval.metrics).map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                {typeof value === "number" ? value.toFixed(4) : String(value)}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Text type="secondary">暂无评测记录</Text>
        )}
      </Card>
    </Space>
  );
}

// ---------------- 知识库 ----------------

function KnowledgeTab() {
  const [data, setData] = useState<AdminKnowledge | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAdminKnowledge());
    } catch (err) {
      setError((err as Error).message || "加载知识库失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <Alert type="error" showIcon message={error} />;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[12, 12]}>
        <Col span={4}>
          <Card size="small" loading={loading}>
            <Statistic title="文档总数" value={data?.documents_total ?? 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" loading={loading}>
            <Statistic title="分块总数" value={data?.chunks_total ?? 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" loading={loading}>
            <Statistic title="失败文档" value={data?.failed_documents ?? 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" loading={loading}>
            <Statistic title="Wiki 空间" value={data?.wiki_spaces ?? 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" loading={loading}>
            <Statistic title="Wiki 页面" value={data?.wiki_pages ?? 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" loading={loading}>
            <Statistic title="悬空链接" value={data?.wiki_dangling_links ?? 0} />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="按来源切片">
        <Table
          rowKey="source_type"
          size="small"
          loading={loading}
          pagination={false}
          dataSource={data?.by_source ?? []}
          columns={[
            { title: "来源", dataIndex: "source_type" },
            { title: "文档数", dataIndex: "documents" },
            { title: "分块数", dataIndex: "chunks" },
          ]}
        />
      </Card>

      <Card size="small" title="Wiki 空间">
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          pagination={false}
          dataSource={data?.spaces ?? []}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "页面数", dataIndex: "page_count" },
            {
              title: "最后同步",
              dataIndex: "last_synced_at",
              render: (v?: string | null) =>
                v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "从未",
            },
          ]}
        />
      </Card>
    </Space>
  );
}

// ---------------- 审计 ----------------

function AuditTab() {
  const [items, setItems] = useState<AdminAuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | undefined>();
  const [requestId, setRequestId] = useState<string | undefined>();

  const load = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchAdminAudit({
          action,
          request_id: requestId,
          page: targetPage,
          page_size: 20,
        });
        setItems(data.items);
        setTotal(data.total);
      } catch (err) {
        setError((err as Error).message || "加载审计失败");
      } finally {
        setLoading(false);
      }
    },
    [action, requestId, page]
  );

  useEffect(() => {
    setPage(1);
    void load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, requestId]);

  const columns: TableColumnsType<AdminAuditItem> = [
    {
      title: "时间",
      dataIndex: "created_at",
      width: 160,
      render: (v?: string | null) => (v ? dayjs(v).format("YYYY-MM-DD HH:mm:ss") : "-"),
    },
    { title: "操作", dataIndex: "action", width: 170 },
    {
      title: "结果",
      dataIndex: "result",
      width: 90,
      render: (r: string) => <Tag color={RESULT_TAG[r] ?? "default"}>{r}</Tag>,
    },
    { title: "资源", dataIndex: "resource_type", width: 110 },
    { title: "资源 ID", dataIndex: "resource_id", width: 200, ellipsis: true },
    { title: "request_id", dataIndex: "request_id", width: 180, ellipsis: true },
    {
      title: "详情",
      dataIndex: "meta",
      render: (meta: Record<string, unknown>) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {JSON.stringify(meta ?? {})}
        </Text>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space wrap>
        <Select
          allowClear
          placeholder="按操作筛选"
          style={{ width: 220 }}
          value={action}
          onChange={setAction}
          options={[
            "user.create",
            "user.role_change",
            "user.disable",
            "user.enable",
            "user.password_reset",
            "user.soft_delete",
            "user.restore",
            "user.force_logout",
            "eval.run_create",
          ].map((v) => ({ value: v, label: v }))}
        />
        <Input.Search
          allowClear
          placeholder="按 request_id 串链路"
          style={{ width: 280 }}
          onSearch={(v) => setRequestId(v || undefined)}
        />
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </Space>
      {error ? <Alert type="error" showIcon message={error} /> : null}
      <Table<AdminAuditItem>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={items}
        scroll={{ x: 1100 }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showSizeChanger: false,
          onChange: (p) => {
            setPage(p);
            void load(p);
          },
        }}
      />
    </Space>
  );
}

// ---------------- 质量看板（评测作业） ----------------

function QualityTab() {
  const [runs, setRuns] = useState<AdminEvalRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [scope, setScope] = useState("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminEvalRuns({ page: 1, page_size: 20 });
      setRuns(data.items);
      setTotal(data.total);
    } catch (err) {
      setError((err as Error).message || "加载评测历史失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const trigger = async () => {
    if (creating) return;
    setCreating(true);
    try {
      await createAdminEvalRun({ source_scope: scope, trigger: "manual" });
      message.success("评测作业已创建（后台执行，可刷新查看进度）");
      await load();
    } catch (err) {
      message.error((err as Error).message || "创建评测失败");
    } finally {
      setCreating(false);
    }
  };

  const columns: TableColumnsType<AdminEvalRun> = [
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (s: string) => (
        <Tag color={STATUS_TAG[s]?.color}>{STATUS_TAG[s]?.label ?? s}</Tag>
      ),
    },
    {
      title: "来源",
      dataIndex: "source_scope",
      width: 90,
      render: (s: string) => SCOPE_LABEL[s] ?? s,
    },
    { title: "触发", dataIndex: "trigger", width: 80 },
    {
      title: "进度",
      dataIndex: "progress",
      width: 90,
      render: (p: number, row) =>
        row.status === "running" ? `${p}%` : p === 100 ? "100%" : "-",
    },
    {
      title: "指标",
      dataIndex: "metrics",
      render: (m: Record<string, number>) =>
        Object.keys(m ?? {}).length === 0 ? (
          <Text type="secondary">-</Text>
        ) : (
          <Text style={{ fontSize: 12 }}>
            {Object.entries(m)
              .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(3) : v}`)
              .join(", ")}
          </Text>
        ),
    },
    {
      title: "错误",
      dataIndex: "error",
      ellipsis: true,
      render: (e?: string | null) => (e ? <Text type="danger">{e}</Text> : "-"),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 160,
      render: (v?: string | null) => (v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-"),
    },
  ];

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space wrap>
        <Select
          value={scope}
          style={{ width: 140 }}
          onChange={setScope}
          options={[
            { value: "all", label: "全部来源" },
            { value: "docs", label: "仅文档" },
            { value: "wiki", label: "仅 Wiki" },
          ]}
        />
        <Button type="primary" icon={<ExperimentOutlined />} loading={creating} onClick={trigger}>
          运行评测
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
        <Text type="secondary">评测在后台执行，运行中刷新可看进度</Text>
      </Space>
      {error ? <Alert type="error" showIcon message={error} /> : null}
      <Table<AdminEvalRun>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={runs}
        scroll={{ x: 1000 }}
        pagination={false}
        footer={() => <Text type="secondary">共 {total} 条</Text>}
      />
    </Space>
  );
}

// ---------------- 外壳 ----------------

interface Props {
  onBack: () => void;
}

export default function AdminPanel({ onBack }: Props) {
  return (
    <div className="admin-wrap">
      <div className="admin-header">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>
          返回
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          管理后台
        </Title>
        <Text type="secondary">质量看板 · 治理与审计（仅管理员）</Text>
      </div>
      <div className="admin-body">
        <Tabs
          defaultActiveKey="overview"
          items={[
            {
              key: "overview",
              label: (
                <span>
                  <DashboardOutlined /> 概览
                </span>
              ),
              children: <OverviewTab />,
            },
            {
              key: "users",
              label: (
                <span>
                  <TeamOutlined /> 用户与用量
                </span>
              ),
              children: <AdminUsers />,
            },
            {
              key: "knowledge",
              label: (
                <span>
                  <BookOutlined /> 知识库
                </span>
              ),
              children: <KnowledgeTab />,
            },
            {
              key: "audit",
              label: (
                <span>
                  <SafetyOutlined /> 审计日志
                </span>
              ),
              children: <AuditTab />,
            },
            {
              key: "quality",
              label: (
                <span>
                  <ExperimentOutlined /> 质量看板
                </span>
              ),
              children: <QualityTab />,
            },
          ]}
        />
      </div>
    </div>
  );
}

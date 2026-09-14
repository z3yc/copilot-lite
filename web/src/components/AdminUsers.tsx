/**
 * 管理后台 · 用户管理（ADMIN_PLAN §9 N1.3b）。
 *
 * 列表 / 搜索筛选 / 新建 / 改角色·启停·重置密码 / 软删除（二次确认+原因）/ 恢复 / 强制下线。
 * 全部写操作走后端审计；非管理员由后端 403 拦截。
 */

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
  type TableColumnsType,
} from "antd";
import {
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";

import {
  createAdminUser,
  deleteAdminUser,
  fetchAdminUsers,
  forceLogoutAdminUser,
  restoreAdminUser,
  updateAdminUser,
  type AdminUserQuery,
} from "../api";
import type { AdminUser } from "../types";

const { Text } = Typography;

const ROLE_LABEL: Record<string, string> = { admin: "管理员", user: "普通用户" };

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState<AdminUserQuery>({ page_size: 20 });
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createForm] = Form.useForm();

  const [editTarget, setEditTarget] = useState<AdminUser | null>(null);
  const [editing, setEditing] = useState(false);
  const [editForm] = Form.useForm();

  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchAdminUsers({ ...query, page: targetPage });
        setUsers(data.items);
        setTotal(data.total);
      } catch (err) {
        setError((err as Error).message || "加载用户失败");
      } finally {
        setLoading(false); // 铁律：busy 必须复位
      }
    },
    [page, query]
  );

  useEffect(() => {
    void load(1);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const submitCreate = async () => {
    if (creating) return;
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      await createAdminUser(values);
      message.success("用户已创建");
      setCreateOpen(false);
      createForm.resetFields();
      await load(1);
    } catch (err) {
      if ((err as { errorFields?: unknown }).errorFields) return; // 校验失败
      message.error((err as Error).message || "创建失败");
    } finally {
      setCreating(false);
    }
  };

  const submitEdit = async () => {
    if (!editTarget || editing) return;
    try {
      const values = await editForm.validateFields();
      const payload: { role?: string; status?: string; password?: string } = {};
      if (values.role && values.role !== editTarget.role) payload.role = values.role;
      if (values.status && values.status !== editTarget.status) payload.status = values.status;
      if (values.password) payload.password = values.password;
      if (Object.keys(payload).length === 0) {
        setEditTarget(null);
        return;
      }
      setEditing(true);
      await updateAdminUser(editTarget.id, payload);
      message.success("已保存");
      setEditTarget(null);
      await load();
    } catch (err) {
      if ((err as { errorFields?: unknown }).errorFields) return;
      message.error((err as Error).message || "保存失败");
    } finally {
      setEditing(false);
    }
  };

  const submitDelete = async () => {
    if (!deleteTarget || deleting) return;
    try {
      setDeleting(true);
      await deleteAdminUser(deleteTarget.id, deleteReason.trim() || undefined);
      message.success("已软删除（可在回收站/此处恢复）");
      setDeleteTarget(null);
      setDeleteReason("");
      await load();
    } catch (err) {
      message.error((err as Error).message || "删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const doRestore = async (user: AdminUser) => {
    try {
      await restoreAdminUser(user.id);
      message.success("已恢复");
      await load();
    } catch (err) {
      message.error((err as Error).message || "恢复失败");
    }
  };

  const doForceLogout = async (user: AdminUser) => {
    try {
      await forceLogoutAdminUser(user.id);
      message.success("已强制下线");
    } catch (err) {
      message.error((err as Error).message || "操作失败");
    }
  };

  const columns: TableColumnsType<AdminUser> = [
    {
      title: "用户名",
      dataIndex: "username",
      render: (name: string, row) => (
        <Space size={6}>
          <span>{name}</span>
          {row.deleted_at ? <Tag color="default">已删除</Tag> : null}
        </Space>
      ),
    },
    {
      title: "角色",
      dataIndex: "role",
      width: 100,
      render: (role: string) => (
        <Tag color={role === "admin" ? "gold" : "blue"}>{ROLE_LABEL[role] ?? role}</Tag>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) =>
        status === "active" ? (
          <Tag color="green">正常</Tag>
        ) : (
          <Tag color="red">已禁用</Tag>
        ),
    },
    {
      title: "模型 Key",
      dataIndex: "has_key",
      width: 100,
      render: (has: boolean) =>
        has ? <Tag color="cyan">已配置</Tag> : <Text type="secondary">未配置</Text>,
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 170,
      render: (value?: string | null) =>
        value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-",
    },
    {
      title: "操作",
      key: "actions",
      width: 250,
      render: (_, row) =>
        row.deleted_at ? (
          <Button size="small" icon={<UndoOutlined />} onClick={() => doRestore(row)}>
            恢复
          </Button>
        ) : (
          <Space size={4}>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Tooltip title="使该用户所有登录立即失效">
              <Button size="small" onClick={() => doForceLogout(row)}>
                强制下线
              </Button>
            </Tooltip>
            <Button size="small" danger onClick={() => setDeleteTarget(row)}>
              删除
            </Button>
          </Space>
        ),
    },
  ];

  const openEdit = (row: AdminUser) => {
    setEditTarget(row);
    editForm.setFieldsValue({ role: row.role, status: row.status, password: "" });
  };

  return (
    <div>
      <Space style={{ marginBottom: 12, flexWrap: "wrap" }}>
        <Input.Search
          allowClear
          placeholder="搜索用户名"
          style={{ width: 200 }}
          onSearch={(value) => setQuery((q) => ({ ...q, q: value || undefined }))}
        />
        <Select
          allowClear
          placeholder="角色"
          style={{ width: 120 }}
          options={[
            { value: "admin", label: "管理员" },
            { value: "user", label: "普通用户" },
          ]}
          onChange={(value) => setQuery((q) => ({ ...q, role: value }))}
        />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 120 }}
          options={[
            { value: "active", label: "正常" },
            { value: "disabled", label: "已禁用" },
          ]}
          onChange={(value) => setQuery((q) => ({ ...q, status: value }))}
        />
        <Select
          value={query.include_deleted ? "true" : "false"}
          style={{ width: 150 }}
          options={[
            { value: "false", label: "不含已删除" },
            { value: "true", label: "含已删除" },
          ]}
          onChange={(value) =>
            setQuery((q) => ({ ...q, include_deleted: value === "true" }))
          }
        />
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
        >
          新建用户
        </Button>
      </Space>

      {error ? (
        <Alert type="error" showIcon style={{ marginBottom: 12 }} message={error} />
      ) : null}

      <Table<AdminUser>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={users}
        scroll={{ x: 900 }}
        pagination={{
          current: page,
          pageSize: query.page_size ?? 20,
          total,
          showSizeChanger: false,
          onChange: (p) => {
            setPage(p);
            void load(p);
          },
        }}
      />

      {/* 新建 */}
      <Modal
        title="新建用户"
        open={createOpen}
        onOk={submitCreate}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        destroyOnHidden
      >
        <Form form={createForm} layout="vertical" initialValues={{ role: "user" }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: "请输入用户名" },
              { pattern: /^[a-zA-Z0-9_]+$/, message: "仅限字母、数字、下划线" },
              { min: 2, max: 64, message: "长度 2-64" },
            ]}
          >
            <Input placeholder="如 alice" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[{ required: true, min: 6, max: 64, message: "密码至少 6 位" }]}
          >
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select
              options={[
                { value: "user", label: "普通用户" },
                { value: "admin", label: "管理员" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑 */}
      <Modal
        title={`编辑用户：${editTarget?.username ?? ""}`}
        open={!!editTarget}
        onOk={submitEdit}
        confirmLoading={editing}
        onCancel={() => setEditTarget(null)}
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="role" label="角色">
            <Select
              options={[
                { value: "user", label: "普通用户" },
                { value: "admin", label: "管理员" },
              ]}
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { value: "active", label: "正常" },
                { value: "disabled", label: "禁用（旧登录立即失效）" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="password"
            label="重置密码"
            rules={[{ min: 6, max: 64, message: "密码至少 6 位" }]}
          >
            <Input.Password placeholder="留空则不修改" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 软删除二次确认 + 原因 */}
      <Modal
        title="删除用户（软删除）"
        open={!!deleteTarget}
        onOk={submitDelete}
        confirmLoading={deleting}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        onCancel={() => {
          setDeleteTarget(null);
          setDeleteReason("");
        }}
        destroyOnHidden
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`将软删除「${deleteTarget?.username ?? ""}」，数据保留可恢复，旧登录立即失效。`}
        />
        <Input.TextArea
          rows={2}
          value={deleteReason}
          placeholder="删除原因（可选，写入审计）"
          onChange={(e) => setDeleteReason(e.target.value)}
        />
      </Modal>
    </div>
  );
}

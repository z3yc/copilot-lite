import { useCallback, useEffect, useState } from "react";
import {
  Avatar,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  BulbOutlined,
  CheckOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  LockOutlined,
  MessageOutlined,
  RobotOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import {
  changePassword,
  clearToken,
  deleteMemory,
  deleteSession,
  deleteTodo,
  fetchMemories,
  fetchProfile,
  fetchSessions,
  fetchTodos,
  updateMemory,
  updateTodo,
} from "../api";
import type { MemoryItem, Profile, Session, TodoItem } from "../types";

const { Title, Text } = Typography;

interface Props {
  onBack: () => void;
  onOpenSession: (sessionId: string) => void;
}

export default function ProfilePage({ onBack, onOpenSession }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState(false);
  const [pwForm] = Form.useForm();

  // 我的会话
  const [sessions, setSessions] = useState<Session[]>([]);
  // 我的待办
  const [todos, setTodos] = useState<TodoItem[]>([]);
  // 我的记忆
  const [memories, setMemories] = useState<MemoryItem[]>([]);

  const loadData = useCallback(() => {
    fetchProfile().then(setProfile).catch(() => {});
    fetchSessions().then(setSessions).catch(() => {});
    fetchTodos().then(setTodos).catch(() => {});
    fetchMemories().then(setMemories).catch(() => {});
  }, []);

  useEffect(() => {
    loadData();
    setLoading(false);
  }, [loadData]);

  const changePw = async (values: { old_password: string; new_password: string }) => {
    setChanging(true);
    try {
      await changePassword(values.old_password, values.new_password);
      message.success("密码已更新");
      pwForm.resetFields();
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setChanging(false);
    }
  };

  const removeSession = async (id: string) => {
    try {
      await deleteSession(id);
      message.success("会话已删除");
      fetchSessions().then(setSessions).catch(() => {});
    } catch (err) {
      message.error(`删除失败: ${err}`);
    }
  };

  const completeTodo = async (id: string) => {
    try {
      await updateTodo(id, { status: "done" });
      fetchTodos().then(setTodos).catch(() => {});
      message.success("已完成");
    } catch (err) {
      message.error(`操作失败: ${err}`);
    }
  };

  const removeTodo = async (id: string) => {
    try {
      await deleteTodo(id);
      fetchTodos().then(setTodos).catch(() => {});
      message.success("已删除");
    } catch (err) {
      message.error(`删除失败: ${err}`);
    }
  };

  const removeMemory = async (id: string) => {
    try {
      await deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      message.success("已忘记这条记忆");
    } catch (err) {
      message.error(`操作失败: ${err}`);
    }
  };

  // 记忆编辑弹窗
  const [editMemory, setEditMemory] = useState<MemoryItem | null>(null);
  const [memForm] = Form.useForm();

  const openEditMemory = (m: MemoryItem) => {
    setEditMemory(m);
    memForm.setFieldsValue({ fact: m.fact, category: m.category });
  };

  const submitMemoryEdit = async () => {
    if (!editMemory) return;
    const values = await memForm.validateFields();
    try {
      const updated = await updateMemory(editMemory.id, values.fact, values.category);
      setMemories((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      message.success("记忆已更新");
      setEditMemory(null);
    } catch (err) {
      message.error(`更新失败: ${err}`);
    }
  };

  if (loading && !profile) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin />
      </div>
    );
  }

  const stats = profile
    ? [
        { title: "会话", value: profile.session_count, icon: <MessageOutlined /> },
        { title: "消息", value: profile.message_count, icon: <RobotOutlined /> },
        { title: "待办", value: profile.todo_count, icon: <TagsOutlined /> },
        { title: "文档", value: profile.doc_count, icon: <FileTextOutlined /> },
        { title: "知识分块", value: profile.chunk_count, icon: <TagsOutlined /> },
      ]
    : [];

  return (
    <div className="profile-wrap">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} style={{ marginBottom: 12 }}>
        返回
      </Button>

      <Tabs
        defaultActiveKey="overview"
        items={[
          {
            key: "overview",
            label: "📊 概览",
            children: (
              <>
                <Card className="profile-card">
                  <Space align="center" size={20}>
                    <Avatar size={72} style={{ backgroundColor: "#4f6ef7", fontSize: 30 }}>
                      {profile?.username?.[0]?.toUpperCase() ?? "U"}
                    </Avatar>
                    <div>
                      <Space size={8} align="center">
                        <Title level={3} style={{ margin: 0 }}>
                          {profile?.username}
                        </Title>
                        {profile?.role === "admin" ? (
                          <Tag color="gold">管理员</Tag>
                        ) : (
                          <Tag color="geekblue">用户</Tag>
                        )}
                      </Space>
                      <div className="dim" style={{ marginTop: 4 }}>
                        注册于{" "}
                        {profile?.created_at
                          ? new Date(profile.created_at).toLocaleString("zh-CN")
                          : "-"}
                      </div>
                    </div>
                  </Space>
                </Card>
                <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
                  {stats.map((s) => (
                    <Col span={8} key={s.title}>
                      <Card size="small">
                        <Statistic title={s.title} value={s.value} prefix={s.icon} />
                      </Card>
                    </Col>
                  ))}
                </Row>
              </>
            ),
          },
          {
            key: "sessions",
            label: "💬 我的会话",
            children: (
              <Card className="profile-card">
                {sessions.length === 0 ? (
                  <Empty description="暂无会话" />
                ) : (
                  <List
                    dataSource={sessions}
                    renderItem={(s) => (
                      <List.Item
                        actions={[
                          <Popconfirm
                            key="del"
                            title="删除该会话？"
                            onConfirm={() => removeSession(s.id)}
                          >
                            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <a onClick={() => onOpenSession(s.id)}>{s.title || "未命名会话"}</a>
                          }
                          description={`${s.message_count} 条消息 · ${
                            s.updated_at
                              ? new Date(s.updated_at).toLocaleString("zh-CN")
                              : "-"
                          }`}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Card>
            ),
          },
          {
            key: "todos",
            label: "📋 我的待办",
            children: (
              <Card className="profile-card">
                {todos.length === 0 ? (
                  <Empty description="暂无待办" />
                ) : (
                  <List
                    dataSource={todos}
                    renderItem={(t) => (
                      <List.Item
                        actions={[
                          t.status !== "done" && (
                            <Button
                              key="done"
                              type="text"
                              size="small"
                              icon={<CheckOutlined />}
                              onClick={() => completeTodo(t.id)}
                            >
                              完成
                            </Button>
                          ),
                          <Popconfirm
                            key="del"
                            title="删除该待办？"
                            onConfirm={() => removeTodo(t.id)}
                          >
                            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <Space>
                              <Text delete={t.status === "done"}>{t.title}</Text>
                              {t.status === "done" ? (
                                <Tag color="success">已完成</Tag>
                              ) : (
                                <Tag color="processing">待办</Tag>
                              )}
                            </Space>
                          }
                          description={`优先级 ${t.priority}${
                            t.due_date ? ` · 截止 ${t.due_date}` : ""
                          }`}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Card>
            ),
          },
          {
            key: "memories",
            label: "🧠 我的记忆",
            children: (
              <Card className="profile-card">
                <div className="dim" style={{ marginBottom: 8 }}>
                  助手从对话中自动记住的关于你的事实与偏好（可删除错误记忆）
                </div>
                {memories.length === 0 ? (
                  <Empty description="还没有记忆——多聊聊天，助手会记住你的偏好" />
                ) : (
                  <List
                    dataSource={memories}
                    renderItem={(m) => (
                      <List.Item
                        actions={[
                          <Button
                            key="edit"
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => openEditMemory(m)}
                          />,
                          <Popconfirm
                            key="del"
                            title="忘记这条记忆？"
                            onConfirm={() => removeMemory(m.id)}
                          >
                            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<BulbOutlined style={{ fontSize: 20, color: "#4f6ef7" }} />}
                          title={m.fact}
                          description={
                            <Space size={8}>
                              <Tag color="geekblue">{m.category_label}</Tag>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                置信度 {(m.confidence * 100).toFixed(0)}%
                              </Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {m.created_at
                                  ? new Date(m.created_at).toLocaleString("zh-CN")
                                  : ""}
                              </Text>
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Card>
            ),
          },
          {
            key: "account",
            label: "🔒 账号设置",
            children: (
              <>
                <Card
                  className="profile-card"
                  title={
                    <Space>
                      <LockOutlined />
                      修改密码
                    </Space>
                  }
                >
                  <Form
                    form={pwForm}
                    layout="vertical"
                    style={{ maxWidth: 360 }}
                    onFinish={changePw}
                  >
                    <Form.Item
                      name="old_password"
                      label="原密码"
                      rules={[{ required: true, message: "请输入原密码" }]}
                    >
                      <Input.Password placeholder="原密码" autoComplete="current-password" />
                    </Form.Item>
                    <Form.Item
                      name="new_password"
                      label="新密码"
                      rules={[
                        { required: true, message: "请输入新密码" },
                        { min: 6, max: 64, message: "至少 6 位" },
                      ]}
                    >
                      <Input.Password placeholder="新密码（至少 6 位）" autoComplete="new-password" />
                    </Form.Item>
                    <Form.Item
                      name="confirm"
                      label="确认新密码"
                      dependencies={["new_password"]}
                      rules={[
                        { required: true, message: "请再次输入新密码" },
                        ({ getFieldValue }) => ({
                          validator(_, value) {
                            if (!value || getFieldValue("new_password") === value) {
                              return Promise.resolve();
                            }
                            return Promise.reject(new Error("两次输入不一致"));
                          },
                        }),
                      ]}
                    >
                      <Input.Password placeholder="再次输入新密码" autoComplete="new-password" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={changing}>
                      更新密码
                    </Button>
                  </Form>
                </Card>

                <Card
                  className="profile-card"
                  style={{ marginTop: 12 }}
                  title="退出登录"
                >
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    退出后将返回登录页，本地数据不会丢失。
                  </Text>
                  <div style={{ marginTop: 10 }}>
                    <Button
                      danger
                      onClick={() => {
                        clearToken();
                        window.location.reload();
                      }}
                    >
                      退出登录
                    </Button>
                  </div>
                </Card>
              </>
            ),
          },
        ]}
      />

      {/* 记忆编辑弹窗 */}
      <Modal
        title="编辑记忆"
        open={!!editMemory}
        onOk={submitMemoryEdit}
        onCancel={() => setEditMemory(null)}
        destroyOnClose
      >
        <Form form={memForm} layout="vertical">
          <Form.Item
            name="fact"
            label="记忆内容"
            rules={[{ required: true, message: "请输入记忆内容" }]}
          >
            <Input.TextArea rows={2} maxLength={300} placeholder="修正记忆描述" />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Select
              options={[
                { value: "preference", label: "偏好" },
                { value: "fact", label: "事实" },
                { value: "background", label: "背景" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

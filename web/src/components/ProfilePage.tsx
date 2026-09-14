import { useCallback, useEffect, useState } from "react";
import {
  AutoComplete,
  Avatar,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
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
  CheckSquareOutlined,
  DashboardOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  LockOutlined,
  MessageOutlined,
  ReloadOutlined,
  RobotOutlined,
  SettingOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import {
  changePassword,
  clearToken,
  deleteLlmSettings,
  deleteMemory,
  deleteSession,
  deleteTodo,
  fetchLlmModels,
  fetchLlmModelsWithKey,
  fetchLlmSettings,
  fetchMemories,
  fetchProfile,
  fetchSessions,
  fetchTodos,
  saveLlmSettings,
  testLlmSettings,
  updateMemory,
  updateTodo,
} from "../api";
import TrashPanel from "./TrashPanel";
import type { LLMSettings, MemoryItem, Profile, Session, TodoItem } from "../types";

const { Title, Text } = Typography;

interface Props {
  onBack: () => void;
  onOpenSession: (sessionId: string, title?: string) => void;
  /** 首次打开时定位到的页签（如未配置 Key 时直达「模型设置」） */
  initialTab?: string;
}

export default function ProfilePage({ onBack, onOpenSession, initialTab }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState(false);
  const [pwForm] = Form.useForm();

  // 模型设置
  const [llm, setLlm] = useState<LLMSettings | null>(null);
  const [llmForm] = Form.useForm();
  const [savingLlm, setSavingLlm] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);

  // 我的会话
  const [sessions, setSessions] = useState<Session[]>([]);
  // 我的待办
  const [todos, setTodos] = useState<TodoItem[]>([]);
  // 我的记忆
  const [memories, setMemories] = useState<MemoryItem[]>([]);

  /** 按已存配置预加载模型候选（未配置/上游不支持时静默，保留手输）。 */
  const loadModelOptions = useCallback(async () => {
    try {
      const res = await fetchLlmModels();
      setModelOptions(res.models ?? []);
    } catch {
      // 未配置 Key 或上游无 /models：忽略，用户可点“获取模型”或手输
    }
  }, []);

  /** 用表单当前（可能未保存）的 Base URL / Key 拉取模型列表。 */
  const fetchModels = async () => {
    const values = llmForm.getFieldsValue(["base_url", "api_key"]);
    setFetchingModels(true);
    try {
      const res = await fetchLlmModelsWithKey({
        base_url: values.base_url,
        api_key: values.api_key || undefined,
      });
      const list = res.models ?? [];
      setModelOptions(list);
      if (!llmForm.getFieldValue("model") && list.length > 0) {
        llmForm.setFieldValue(
          "model",
          res.current && list.includes(res.current) ? res.current : list[0]
        );
      }
      message.success(`已获取 ${list.length} 个可用模型`);
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setFetchingModels(false);
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      fetchProfile().then(setProfile),
      fetchSessions().then(setSessions),
      fetchTodos().then(setTodos),
      fetchMemories().then(setMemories),
      fetchLlmSettings().then((s) => {
        setLlm(s);
        llmForm.setFieldsValue({
          base_url: s.base_url,
          model: s.model,
          temperature: s.temperature,
          max_tokens: s.max_tokens,
        });
        if (s.api_key_set) void loadModelOptions();
      }),
    ]);
    const failures = results.filter((r) => r.status === "rejected");
    if (failures.length > 0) {
      console.error(
        "个人主页部分数据加载失败",
        failures.map((f) => (f as PromiseRejectedResult).reason)
      );
      message.error("部分数据加载失败，请稍后重试");
    }
    setLoading(false);
  }, [llmForm, loadModelOptions]);

  useEffect(() => {
    loadData();
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

  const saveLlm = async (values: {
    base_url: string;
    model: string;
    api_key?: string;
    temperature: number;
    max_tokens: number;
  }) => {
    setSavingLlm(true);
    try {
      const saved = await saveLlmSettings({
        base_url: values.base_url,
        model: values.model,
        temperature: values.temperature,
        max_tokens: values.max_tokens,
        // 留空则不修改已存 Key
        ...(values.api_key ? { api_key: values.api_key } : {}),
      });
      setLlm(saved);
      llmForm.setFieldValue("api_key", "");
      void loadModelOptions();
      message.success("模型配置已保存");
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setSavingLlm(false);
    }
  };

  const testLlm = async () => {
    const values = await llmForm.validateFields(["base_url", "model"]);
    setTestingLlm(true);
    try {
      const res = await testLlmSettings({
        base_url: values.base_url,
        model: values.model,
        api_key: llmForm.getFieldValue("api_key") || undefined,
      });
      if (res.ok) message.success(res.message);
      else message.error(res.message);
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setTestingLlm(false);
    }
  };

  const resetLlm = async () => {
    try {
      await deleteLlmSettings();
      const s = await fetchLlmSettings();
      setLlm(s);
      llmForm.setFieldsValue({
        base_url: s.base_url,
        model: s.model,
        temperature: s.temperature,
        max_tokens: s.max_tokens,
        api_key: "",
      });
      message.success("已恢复默认模型配置");
    } catch (err) {
      message.error(`${err}`);
    }
  };

  const removeSession = async (id: string) => {
    try {
      await deleteSession(id);
      message.success("会话已删除");
      fetchSessions()
        .then(setSessions)
        .catch((err) => console.error("刷新会话列表失败", err));
    } catch (err) {
      message.error(`删除失败: ${err}`);
    }
  };

  const completeTodo = async (id: string) => {
    try {
      await updateTodo(id, { status: "done" });
      fetchTodos()
        .then(setTodos)
        .catch((err) => console.error("刷新待办列表失败", err));
      message.success("已完成");
    } catch (err) {
      message.error(`操作失败: ${err}`);
    }
  };

  const removeTodo = async (id: string) => {
    try {
      await deleteTodo(id);
      fetchTodos()
        .then(setTodos)
        .catch((err) => console.error("刷新待办列表失败", err));
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
        defaultActiveKey={initialTab ?? "overview"}
        items={[
          {
            key: "overview",
            label: (
              <span>
                <DashboardOutlined /> 概览
              </span>
            ),
            children: (
              <>
                <Card className="profile-card">
                  <Space align="center" size={20}>
                    <Avatar
                      size={72}
                      style={{ backgroundColor: "var(--color-primary)", fontSize: 30 }}
                    >
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
                    <Col xs={12} sm={8} key={s.title}>
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
            label: (
              <span>
                <MessageOutlined /> 我的会话
              </span>
            ),
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
                            title="删除该会话？可在回收站恢复"
                            onConfirm={() => removeSession(s.id)}
                          >
                            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <a onClick={() => onOpenSession(s.id, s.title)}>
                              {s.title || "未命名会话"}
                            </a>
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
            label: (
              <span>
                <CheckSquareOutlined /> 我的待办
              </span>
            ),
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
                            title="删除该待办？可在回收站恢复"
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
            label: (
              <span>
                <BulbOutlined /> 我的记忆
              </span>
            ),
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
                            title="忘记这条记忆？可在回收站恢复"
                            onConfirm={() => removeMemory(m.id)}
                          >
                            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={
                            <BulbOutlined
                              style={{ fontSize: 20, color: "var(--color-primary)" }}
                            />
                          }
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
            key: "model",
            label: (
              <span>
                <SettingOutlined /> 模型设置
              </span>
            ),
            children: (
              <Card
                className="profile-card"
                title={
                  <Space>
                    <RobotOutlined />
                    模型配置
                  </Space>
                }
              >
                <div className="dim" style={{ marginBottom: 12, fontSize: 13 }}>
                  当前来源：
                  {llm?.source === "user"
                    ? "个人配置"
                    : llm?.source === "env"
                      ? "环境变量默认"
                      : "未配置"}
                  {llm?.api_key_set
                    ? ` · API Key ${llm.api_key_preview}`
                    : " · 未设置 API Key"}
                </div>
                <Form
                  form={llmForm}
                  layout="vertical"
                  style={{ maxWidth: 440 }}
                  onFinish={saveLlm}
                  initialValues={{ temperature: 0.7, max_tokens: 2048 }}
                >
                  <Form.Item
                    name="base_url"
                    label="Base URL"
                    rules={[{ required: true, message: "请输入 Base URL" }]}
                  >
                    <Input placeholder="https://api.deepseek.com" />
                  </Form.Item>
                  <Form.Item label="模型名称" required>
                    <Space.Compact style={{ width: "100%" }}>
                      <Form.Item
                        name="model"
                        noStyle
                        rules={[{ required: true, message: "请输入或获取模型名称" }]}
                      >
                        <AutoComplete
                          options={modelOptions.map((m) => ({ value: m }))}
                          placeholder="deepseek-chat（可点右侧「获取模型」拉取列表）"
                          filterOption={(input, option) =>
                            String(option?.value ?? "")
                              .toLowerCase()
                              .includes(input.toLowerCase())
                          }
                        />
                      </Form.Item>
                      <Button
                        icon={<ReloadOutlined />}
                        loading={fetchingModels}
                        onClick={fetchModels}
                      >
                        获取模型
                      </Button>
                    </Space.Compact>
                  </Form.Item>
                  <Form.Item
                    name="api_key"
                    label="API Key"
                    extra="留空不修改已存 Key；填写新值将覆盖（加密存储，不回显明文）"
                  >
                    <Input.Password
                      autoComplete="off"
                      placeholder={
                        llm?.api_key_set
                          ? `已配置（${llm.api_key_preview}），留空不修改`
                          : "sk-..."
                      }
                    />
                  </Form.Item>
                  <Space size={16} align="start">
                    <Form.Item name="temperature" label="温度">
                      <InputNumber min={0} max={2} step={0.1} />
                    </Form.Item>
                    <Form.Item name="max_tokens" label="最大 tokens">
                      <InputNumber min={1} max={32768} step={256} />
                    </Form.Item>
                  </Space>
                  <div style={{ marginTop: 8 }}>
                    <Space>
                      <Button type="primary" htmlType="submit" loading={savingLlm}>
                        保存
                      </Button>
                      <Button onClick={testLlm} loading={testingLlm}>
                        测试连接
                      </Button>
                      <Popconfirm title="恢复环境变量默认配置？" onConfirm={resetLlm}>
                        <Button danger>恢复默认</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                </Form>
              </Card>
            ),
          },
          {
            key: "trash",
            label: (
              <span>
                <DeleteOutlined /> 回收站
              </span>
            ),
            children: <TrashPanel />,
          },
          {
            key: "account",
            label: (
              <span>
                <LockOutlined /> 账号设置
              </span>
            ),
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
        destroyOnHidden
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

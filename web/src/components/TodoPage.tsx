import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Button,
  Checkbox,
  DatePicker,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  FieldTimeOutlined,
  FileTextOutlined,
  FireOutlined,
  InboxOutlined,
  PlusOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  aiCreateTodo,
  createTodo,
  deleteTodo,
  fetchCategories,
  fetchTodos,
  updateTodo,
} from "../api";
import type { Category, TodoItem } from "../types";
import { keyboardActivate } from "../utils/a11y";
import SiderPortal from "./SiderPortal";

const { Text } = Typography;

// 时间分组与高亮
type DueGroup = "今天" | "本周" | "未来" | "已过期" | "无日期";
const GROUP_ORDER: DueGroup[] = ["已过期", "今天", "本周", "未来", "无日期"];

function dueInfo(due?: string | null): { group: DueGroup; tone: string } {
  if (!due) return { group: "无日期", tone: "" };
  const d = dayjs(due).startOf("day");
  const today = dayjs().startOf("day");
  if (d.isBefore(today)) return { group: "已过期", tone: "overdue" }; // 红
  if (d.isSame(today, "day")) return { group: "今天", tone: "today" }; // 橙
  if (d.isBefore(today.add(7 - today.day(), "day").add(1, "day"))) {
    return { group: "本周", tone: "week" }; // 黄
  }
  return { group: "未来", tone: "" };
}

const PRIORITY_LABEL = ["", "紧急", "高", "中", "低", "很低"];

export default function TodoPage() {
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [aiText, setAiText] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  // 筛选
  const [view, setView] = useState<string>("all"); // all/today/week/future/overdue/nodate/done
  const [catFilter, setCatFilter] = useState<string | null>(null);

  // 弹窗
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TodoItem | null>(null);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    try {
      const [t, c] = await Promise.all([fetchTodos(), fetchCategories()]);
      setTodos(t);
      setCategories(c);
    } catch (err) {
      message.error(`加载失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 计数（未完成）
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    todos
      .filter((t) => t.status === "pending")
      .forEach((t) => {
        const g = dueInfo(t.due_date).group;
        c[g] = (c[g] ?? 0) + 1;
        if (t.category_id) c[`cat:${t.category_id}`] = (c[`cat:${t.category_id}`] ?? 0) + 1;
      });
    c.all = todos.filter((t) => t.status === "pending").length;
    c.done = todos.filter((t) => t.status === "done").length;
    return c;
  }, [todos]);

  // 过滤
  const filtered = useMemo(() => {
    let list = todos;
    if (view === "done") {
      list = list.filter((t) => t.status === "done");
    } else {
      list = list.filter((t) => t.status === "pending");
      if (view !== "all") {
        if (view === "nodate") {
          list = list.filter((t) => !t.due_date);
        } else {
          list = list.filter((t) => dueInfo(t.due_date).group === view);
        }
      }
    }
    if (catFilter) list = list.filter((t) => t.category_id === catFilter);
    return list;
  }, [todos, view, catFilter]);

  // 分组
  const groups = useMemo(() => {
    const g = new Map<DueGroup, TodoItem[]>();
    filtered.forEach((t) => {
      const { group } = dueInfo(t.due_date);
      if (!g.has(group)) g.set(group, []);
      g.get(group)!.push(t);
    });
    return GROUP_ORDER.filter((k) => g.has(k)).map((k) => [k, g.get(k)!] as const);
  }, [filtered]);

  const toggleDone = async (t: TodoItem) => {
    try {
      await updateTodo(t.id, { status: t.status === "done" ? "pending" : "done" });
      load();
    } catch (err) {
      message.error(`操作失败: ${err}`);
    }
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (t: TodoItem) => {
    setEditing(t);
    form.setFieldsValue({
      title: t.title,
      category_id: t.category_id,
      priority: t.priority,
      due_date: t.due_date ? dayjs(t.due_date) : null,
      tags: t.tags ?? [],
    });
    setModalOpen(true);
  };

  const submitForm = async () => {
    const values = await form.validateFields();
    const payload = {
      title: values.title,
      category_id: values.category_id ?? null,
      priority: values.priority ?? 3,
      due_date: values.due_date ? values.due_date.format("YYYY-MM-DD") : null,
      tags: values.tags ?? [],
    };
    try {
      if (editing) {
        await updateTodo(editing.id, payload);
        message.success("已更新");
      } else {
        await createTodo(payload);
        message.success("已创建");
      }
      setModalOpen(false);
      load();
    } catch (err) {
      message.error(`${err}`);
    }
  };

  const aiAdd = async () => {
    const text = aiText.trim();
    if (!text || aiLoading) return;
    setAiLoading(true);
    try {
      const t = await aiCreateTodo(text);
      message.success(`AI 已创建「${t.title}」${t.category_name ? `（${t.category_name}）` : ""}`);
      setAiText("");
      load();
    } catch (err) {
      message.error(`AI 创建失败: ${err}`);
    } finally {
      setAiLoading(false);
    }
  };

  const navItems: { key: string; label: string; icon: ReactNode }[] = [
    { key: "all", label: "全部待办", icon: <InboxOutlined /> },
    {
      key: "today",
      label: "今天",
      icon: <ClockCircleOutlined style={{ color: "var(--color-danger)" }} />,
    },
    {
      key: "week",
      label: "本周",
      icon: <ClockCircleOutlined style={{ color: "var(--color-warning)" }} />,
    },
    { key: "future", label: "未来", icon: <CalendarOutlined /> },
    {
      key: "overdue",
      label: "已过期",
      icon: <FieldTimeOutlined style={{ color: "var(--color-danger)" }} />,
    },
    { key: "nodate", label: "无日期", icon: <FileTextOutlined /> },
    {
      key: "done",
      label: "已完成",
      icon: <CheckCircleOutlined style={{ color: "var(--color-success)" }} />,
    },
  ];

  return (
    <div className="todo-page">
      {/* 导航目录：portal 到「工作区」侧栏 */}
      <SiderPortal>
      <div className="todo-nav">
        {navItems.map((n) => (
          <div
            key={n.key}
            className={`todo-nav-item ${view === n.key && !catFilter ? "active" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={`筛选：${n.label}`}
            onClick={() => {
              setView(n.key);
              setCatFilter(null);
            }}
            onKeyDown={keyboardActivate(() => {
              setView(n.key);
              setCatFilter(null);
            })}
          >
            <span>
              {n.icon} {n.label}
            </span>
            <span className="todo-nav-count">{counts[n.key] ?? 0}</span>
          </div>
        ))}
        <div className="todo-nav-divider" />
        {categories.map((c) => (
          <div
            key={c.id}
            className={`todo-nav-item ${catFilter === c.id ? "active" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={`按分类筛选：${c.name}`}
            onClick={() => {
              setCatFilter(c.id);
              setView("all");
            }}
            onKeyDown={keyboardActivate(() => {
              setCatFilter(c.id);
              setView("all");
            })}
          >
            <span>
              <span className="cat-dot" style={{ background: c.color }} />
              {c.name}
            </span>
            <span className="todo-nav-count">{counts[`cat:${c.id}`] ?? 0}</span>
          </div>
        ))}
      </div>
      </SiderPortal>

      {/* 主区 */}
      <div className="todo-main">
        <div className="todo-toolbar">
          <Space.Compact style={{ width: "60%", maxWidth: 560 }}>
            <Input
              prefix={<RobotOutlined style={{ color: "var(--color-primary)" }} />}
              placeholder='AI 快速添加："明天下午3点买菜 生活 #采购"'
              value={aiText}
              onChange={(e) => setAiText(e.target.value)}
              onPressEnter={aiAdd}
              disabled={aiLoading}
            />
            <Button type="primary" onClick={aiAdd} loading={aiLoading}>
              AI 添加
            </Button>
          </Space.Compact>
          <Button type="primary" ghost icon={<PlusOutlined />} onClick={openCreate}>
            新建待办
          </Button>
        </div>

        <div className="todo-list">
          {loading ? (
            <div style={{ textAlign: "center", padding: 40 }}>
              <Spin />
            </div>
          ) : filtered.length === 0 ? (
            <div className="dim" style={{ textAlign: "center", padding: 40 }}>
              这里空空如也，用上方 AI 框或"新建待办"添加吧
            </div>
          ) : (
            groups.map(([group, items]) => (
              <div key={group} className="todo-group">
                <div className="todo-group-title">
                  {group}
                  <span className="dim">（{items.length}）</span>
                </div>
                {items.map((t) => {
                  const { tone } = dueInfo(t.due_date);
                  return (
                    <div key={t.id} className={`todo-item ${tone}`}>
                      <Checkbox
                        checked={t.status === "done"}
                        onChange={() => toggleDone(t)}
                      />
                      <div className="todo-content">
                        <div className={`todo-title ${t.status === "done" ? "done" : ""}`}>
                          {t.title}
                        </div>
                        <div className="todo-meta">
                          {t.category_name && (
                            <Tag
                              style={{
                                color: t.category_color ?? undefined,
                                borderColor: t.category_color ?? undefined,
                              }}
                            >
                              {t.category_name}
                            </Tag>
                          )}
                          {t.tags?.map((tag) => (
                            <Tag key={tag} color="geekblue">
                              #{tag}
                            </Tag>
                          ))}
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {t.due_date ? `${dueInfo(t.due_date).group} ${t.due_date}` : "无日期"}
                          </Text>
                        </div>
                      </div>
                      <span
                        className="todo-priority"
                        role="img"
                        aria-label={`优先级：${PRIORITY_LABEL[t.priority]}`}
                        title={`优先级 ${PRIORITY_LABEL[t.priority]}`}
                      >
                        {Array.from({ length: Math.max(0, 4 - t.priority) }, (_, i) => (
                          <FireOutlined key={i} style={{ color: "var(--color-danger)" }} />
                        ))}
                      </span>
                      <Button
                        type="text"
                        size="small"
                        aria-label="编辑待办"
                        icon={<EditOutlined />}
                        onClick={() => openEdit(t)}
                      />
                      <Popconfirm title="删除该待办？" onConfirm={() => deleteTodo(t.id).then(load)}>
                        <Button
                          type="text"
                          size="small"
                          danger
                          aria-label="删除待办"
                          icon={<DeleteOutlined />}
                        />
                      </Popconfirm>
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editing ? "编辑待办" : "新建待办"}
        open={modalOpen}
        onOk={submitForm}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}>
            <Input placeholder="要做什么？" maxLength={255} />
          </Form.Item>
          <Form.Item name="category_id" label="分类">
            <Select
              placeholder="选择分类"
              allowClear
              options={categories.map((c) => ({
                value: c.id,
                label: `${c.name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue={3}>
            <Select
              options={[1, 2, 3, 4, 5].map((p) => ({
                value: p,
                label: `${p} - ${PRIORITY_LABEL[p]}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入后回车添加标签" open={false} suffixIcon={null} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

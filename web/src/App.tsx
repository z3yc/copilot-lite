import {
  useCallback,
  useEffect,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  App as AntApp,
  Avatar,
  Button,
  ConfigProvider,
  Layout,
  Space,
  Tabs,
  Tooltip,
  theme,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import {
  BookOutlined,
  BulbOutlined,
  CheckSquareOutlined,
  LogoutOutlined,
  MessageOutlined,
  MoonOutlined,
  PartitionOutlined,
} from "@ant-design/icons";
import { clearToken, fetchMessages, fetchProfile, getToken } from "./api";
import { BRAND_PRIMARY, BRAND_RADIUS } from "./theme";
import { keyboardActivate } from "./utils/a11y";
import ChatPanel from "./components/ChatPanel";
import DocCategoryNav from "./components/DocCategoryNav";
import KbPanel from "./components/KbPanel";
import LoginPage from "./components/LoginPage";
import ProfilePage from "./components/ProfilePage";
import SessionList from "./components/SessionList";
import TodoPage from "./components/TodoPage";
import WikiPanel from "./components/WikiPanel";
import type { ChatMessage, Profile } from "./types";

const { Sider, Content } = Layout;

// 侧栏可拖拽调宽范围与默认值（宽度记忆到 localStorage）
const SIDER_MIN = 240;
const SIDER_MAX = 560;
const SIDER_DEFAULT = 300;
const SIDER_WIDTH_KEY = "kb-sider-width";

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!getToken());
  const [tab, setTab] = useState<"chat" | "kb" | "wiki" | "todo">("chat");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [activeCat, setActiveCat] = useState<string>("all");
  const [showProfile, setShowProfile] = useState(false);
  const [me, setMe] = useState<Profile | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [siderWidth, setSiderWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem(SIDER_WIDTH_KEY));
    return saved >= SIDER_MIN && saved <= SIDER_MAX ? saved : SIDER_DEFAULT;
  });
  const [dark, setDark] = useState<boolean>(
    () => localStorage.getItem("kb-theme") === "dark"
  );

  // 令牌过期事件（api.ts 401 时触发）
  useEffect(() => {
    const onExpired = () => setAuthed(false);
    window.addEventListener("auth-expired", onExpired);
    return () => window.removeEventListener("auth-expired", onExpired);
  }, []);

  // 登录后拉取当前用户，侧栏展示真实昵称/头像，而非写死
  useEffect(() => {
    if (!authed) {
      setMe(null);
      return;
    }
    let cancelled = false;
    fetchProfile()
      .then((p) => {
        if (!cancelled) setMe(p);
      })
      .catch((err) => console.error("加载当前用户失败", err));
    return () => {
      cancelled = true;
    };
  }, [authed]);

  const persistSiderWidth = useCallback((w: number) => {
    const next = Math.min(SIDER_MAX, Math.max(SIDER_MIN, w));
    setSiderWidth(next);
    localStorage.setItem(SIDER_WIDTH_KEY, String(next));
  }, []);

  // 拖拽分隔条调整侧栏宽度（指针事件 + 指针捕获，拖动更稳）
  const startSiderResize = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const el = e.currentTarget;
    const startX = e.clientX;
    const startW = siderWidth;
    el.setPointerCapture?.(e.pointerId);
    const onMove = (ev: PointerEvent) => {
      setSiderWidth(
        Math.min(SIDER_MAX, Math.max(SIDER_MIN, startW + (ev.clientX - startX)))
      );
    };
    const onUp = (ev: PointerEvent) => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
      try {
        el.releasePointerCapture?.(ev.pointerId);
      } catch {
        // 指针已释放：忽略
      }
      setSiderWidth((w) => {
        localStorage.setItem(SIDER_WIDTH_KEY, String(w));
        return w;
      });
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
  };

  // 键盘微调：←/→ 调整，Shift 加速，Home/End 到边界
  const onSiderKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 48 : 16;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      persistSiderWidth(siderWidth - step);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      persistSiderWidth(siderWidth + step);
    } else if (e.key === "Home") {
      e.preventDefault();
      persistSiderWidth(SIDER_MIN);
    } else if (e.key === "End") {
      e.preventDefault();
      persistSiderWidth(SIDER_MAX);
    }
  };

  const logout = () => {
    clearToken();
    setAuthed(false);
    setSessionId(null);
    setMessages([]);
  };

  useEffect(() => {
    document.body.classList.toggle("dark", dark);
    localStorage.setItem("kb-theme", dark ? "dark" : "light");
  }, [dark]);

  const selectSession = useCallback(async (id: string, title?: string) => {
    setTab("chat");
    setSessionId(id);
    setSessionTitle(title ?? null);
    try {
      setMessages(await fetchMessages(id));
    } catch (err) {
      console.error("加载历史失败", err);
      setMessages([]);
    }
  }, []);

  const newSession = useCallback(() => {
    setSessionId(null);
    setSessionTitle(null);
    setMessages([]);
    setTab("chat");
  }, []);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: BRAND_PRIMARY,
          borderRadius: BRAND_RADIUS,
        },
      }}
    >
      <AntApp>
        {!authed ? (
          <LoginPage onSuccess={() => setAuthed(true)} />
        ) : (
        <Layout style={{ height: "100vh" }}>
          <Sider
            width={siderWidth}
            theme="light"
            breakpoint="lg"
            collapsedWidth={0}
            onCollapse={setCollapsed}
            style={{
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              background: "var(--panel)",
            }}
          >
            <div style={{ padding: "12px 12px 0" }}>
              <Tabs
                activeKey={tab}
                onChange={(k) => setTab(k as "chat" | "kb" | "wiki" | "todo")}
                centered
                items={[
                  {
                    key: "chat",
                    label: (
                      <span>
                        <MessageOutlined /> 对话
                      </span>
                    ),
                  },
                  {
                    key: "kb",
                    label: (
                      <span>
                        <BookOutlined /> 知识库
                      </span>
                    ),
                  },
                  {
                    key: "wiki",
                    label: (
                      <span>
                        <PartitionOutlined /> Wiki
                      </span>
                    ),
                  },
                  {
                    key: "todo",
                    label: (
                      <span>
                        <CheckSquareOutlined /> 待办
                      </span>
                    ),
                  },
                ]}
              />
            </div>
            {tab === "chat" ? (
              <SessionList
                activeId={sessionId}
                onSelect={selectSession}
                onNew={newSession}
              />
            ) : tab === "kb" ? (
              <DocCategoryNav activeCat={activeCat} onChange={setActiveCat} />
            ) : tab === "wiki" ? (
              <div className="dim" style={{ textAlign: "center", padding: 24 }}>
                Wiki 空间与页面（右侧操作）
              </div>
            ) : (
              <div className="dim" style={{ textAlign: "center", padding: 24 }}>
                待办工作区（右侧操作）
              </div>
            )}
            <div
              style={{
                marginTop: "auto", // 始终钉在侧栏底部（左下角）
                padding: 12,
                borderTop: "1px solid var(--border)",
              }}
            >
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <Space
                  size={8}
                  role="button"
                  tabIndex={0}
                  aria-label="打开个人主页"
                  style={{ cursor: "pointer" }}
                  onClick={() => setShowProfile(true)}
                  onKeyDown={keyboardActivate(() => setShowProfile(true))}
                  title="个人主页"
                >
                  <Avatar size={28} style={{ backgroundColor: "var(--color-primary)" }}>
                    {(me?.username?.[0] ?? "U").toUpperCase()}
                  </Avatar>
                  <span style={{ fontSize: 13, color: "var(--text)" }}>
                    {me?.username ?? "未登录"}
                  </span>
                </Space>
                <Space size={4}>
                  <Tooltip title={dark ? "切换到亮色模式" : "切换到暗色模式"}>
                    <Button
                      type="text"
                      size="small"
                      aria-label={dark ? "切换到亮色模式" : "切换到暗色模式"}
                      icon={dark ? <BulbOutlined /> : <MoonOutlined />}
                      onClick={() => setDark(!dark)}
                    />
                  </Tooltip>
                  <Tooltip title="退出登录">
                    <Button
                      type="text"
                      size="small"
                      aria-label="退出登录"
                      icon={<LogoutOutlined />}
                      onClick={logout}
                    />
                  </Tooltip>
                </Space>
              </Space>
            </div>
          </Sider>
          {!collapsed && (
            <div
              className="sider-resizer"
              role="separator"
              aria-orientation="vertical"
              aria-label="调整侧栏宽度"
              aria-valuemin={SIDER_MIN}
              aria-valuemax={SIDER_MAX}
              aria-valuenow={siderWidth}
              tabIndex={0}
              title="拖动调整宽度（方向键微调）"
              onPointerDown={startSiderResize}
              onKeyDown={onSiderKeyDown}
            />
          )}
          <Content style={{ display: "flex", overflow: "hidden" }}>
            {showProfile ? (
              <ProfilePage
                onBack={() => setShowProfile(false)}
                onOpenSession={(id, title) => {
                  setShowProfile(false);
                  selectSession(id, title);
                }}
              />
            ) : tab === "chat" ? (
              <ChatPanel
                sessionId={sessionId}
                sessionTitle={sessionTitle}
                initialMessages={messages}
                onSessionCreated={setSessionId}
                onNewSession={newSession}
                busy={busy}
                setBusy={setBusy}
              />
            ) : tab === "kb" ? (
              <KbPanel activeCat={activeCat} onCatChange={setActiveCat} />
            ) : tab === "wiki" ? (
              <WikiPanel />
            ) : (
              <TodoPage />
            )}
          </Content>
        </Layout>
        )}
      </AntApp>
    </ConfigProvider>
  );
}

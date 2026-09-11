import { useCallback, useEffect, useState } from "react";
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
import { BulbOutlined, LogoutOutlined, MoonOutlined } from "@ant-design/icons";
import { clearToken, fetchMessages, getToken } from "./api";
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
import type { ChatMessage } from "./types";

const { Sider, Content } = Layout;

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!getToken());
  const [tab, setTab] = useState<"chat" | "kb" | "wiki" | "todo">("chat");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [activeCat, setActiveCat] = useState<string>("all");
  const [showProfile, setShowProfile] = useState(false);
  const [dark, setDark] = useState<boolean>(
    () => localStorage.getItem("kb-theme") === "dark"
  );

  // 令牌过期事件（api.ts 401 时触发）
  useEffect(() => {
    const onExpired = () => setAuthed(false);
    window.addEventListener("auth-expired", onExpired);
    return () => window.removeEventListener("auth-expired", onExpired);
  }, []);

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

  const selectSession = useCallback(async (id: string) => {
    setTab("chat");
    setSessionId(id);
    try {
      setMessages(await fetchMessages(id));
    } catch (err) {
      console.error("加载历史失败", err);
      setMessages([]);
    }
  }, []);

  const newSession = useCallback(() => {
    setSessionId(null);
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
            width={280}
            theme="light"
            style={{
              borderRight: "1px solid var(--border)",
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
                  { key: "chat", label: "💬 对话" },
                  { key: "kb", label: "📚 知识库" },
                  { key: "wiki", label: "🕸️ Wiki" },
                  { key: "todo", label: "📋 待办" },
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
            <div style={{ padding: 12, borderTop: "1px solid var(--border)" }}>
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
                    {(getToken() ? "青" : "U")[0]}
                  </Avatar>
                  <span style={{ fontSize: 13, color: "var(--text)" }}>
                    青木的助理
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
          <Content style={{ display: "flex", overflow: "hidden" }}>
            {showProfile ? (
              <ProfilePage
                onBack={() => setShowProfile(false)}
                onOpenSession={(id) => {
                  setShowProfile(false);
                  selectSession(id);
                }}
              />
            ) : tab === "chat" ? (
              <ChatPanel
                sessionId={sessionId}
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

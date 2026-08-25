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
import ChatPanel from "./components/ChatPanel";
import DocCategoryNav from "./components/DocCategoryNav";
import KbPanel from "./components/KbPanel";
import LoginPage from "./components/LoginPage";
import ProfilePage from "./components/ProfilePage";
import SessionList from "./components/SessionList";
import type { ChatMessage } from "./types";

const { Sider, Content } = Layout;

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!getToken());
  const [tab, setTab] = useState<"chat" | "kb">("chat");
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
          colorPrimary: "#4f6ef7",
          borderRadius: 10,
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
                onChange={(k) => setTab(k as "chat" | "kb")}
                centered
                items={[
                  { key: "chat", label: "💬 对话" },
                  { key: "kb", label: "📚 知识库" },
                ]}
              />
            </div>
            {tab === "chat" ? (
              <SessionList
                activeId={sessionId}
                onSelect={selectSession}
                onNew={newSession}
              />
            ) : (
              <DocCategoryNav activeCat={activeCat} onChange={setActiveCat} />
            )}
            <div style={{ padding: 12, borderTop: "1px solid var(--border)" }}>
              <Space direction="vertical" style={{ width: "100%" }} size={8}>
                <Space
                  style={{ width: "100%", justifyContent: "space-between" }}
                >
                  <Space
                    size={8}
                    style={{ cursor: "pointer" }}
                    onClick={() => setShowProfile(true)}
                    title="个人主页"
                  >
                    <Avatar size={28} style={{ backgroundColor: "#4f6ef7" }}>
                      {(getToken() ? "青" : "U")[0]}
                    </Avatar>
                    <span style={{ fontSize: 13, color: "var(--text)" }}>
                      青木的助理
                    </span>
                  </Space>
                  <Tooltip title="退出登录">
                    <Button
                      type="text"
                      size="small"
                      icon={<LogoutOutlined />}
                      onClick={logout}
                    />
                  </Tooltip>
                </Space>
                <Tooltip title={dark ? "切换到亮色模式" : "切换到暗色模式"}>
                  <Button
                    block
                    size="small"
                    icon={dark ? <BulbOutlined /> : <MoonOutlined />}
                    onClick={() => setDark(!dark)}
                  >
                    {dark ? "亮色模式" : "暗色模式"}
                  </Button>
                </Tooltip>
              </Space>
            </div>
          </Sider>
          <Content style={{ display: "flex", overflow: "hidden" }}>
            {showProfile ? (
              <ProfilePage onBack={() => setShowProfile(false)} />
            ) : tab === "chat" ? (
              <ChatPanel
                sessionId={sessionId}
                initialMessages={messages}
                onSessionCreated={setSessionId}
                onNewSession={newSession}
                busy={busy}
                setBusy={setBusy}
              />
            ) : (
              <KbPanel activeCat={activeCat} onCatChange={setActiveCat} />
            )}
          </Content>
        </Layout>
        )}
      </AntApp>
    </ConfigProvider>
  );
}

import { useCallback, useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  ConfigProvider,
  Layout,
  Tabs,
  theme,
  Tooltip,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import { BulbOutlined, MoonOutlined } from "@ant-design/icons";
import { fetchMessages } from "./api";
import ChatPanel from "./components/ChatPanel";
import DocCategoryNav from "./components/DocCategoryNav";
import KbPanel from "./components/KbPanel";
import SessionList from "./components/SessionList";
import type { ChatMessage } from "./types";

const { Sider, Content } = Layout;

export default function App() {
  const [tab, setTab] = useState<"chat" | "kb">("chat");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [activeCat, setActiveCat] = useState<string>("all");
  const [dark, setDark] = useState<boolean>(
    () => localStorage.getItem("kb-theme") === "dark"
  );

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
              <Tooltip title={dark ? "切换到亮色模式" : "切换到暗色模式"}>
                <Button
                  block
                  icon={dark ? <BulbOutlined /> : <MoonOutlined />}
                  onClick={() => setDark(!dark)}
                >
                  {dark ? "亮色模式" : "暗色模式"}
                </Button>
              </Tooltip>
            </div>
          </Sider>
          <Content style={{ display: "flex", overflow: "hidden" }}>
            {tab === "chat" ? (
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
      </AntApp>
    </ConfigProvider>
  );
}

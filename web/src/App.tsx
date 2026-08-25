import { useCallback, useEffect, useState } from "react";
import { App as AntApp, Card, ConfigProvider, Layout, Statistic, Tabs, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { FileTextOutlined, MessageOutlined } from "@ant-design/icons";
import { fetchDocs, fetchMessages } from "./api";
import ChatPanel from "./components/ChatPanel";
import KbPanel from "./components/KbPanel";
import SessionList from "./components/SessionList";
import type { ChatMessage, DocItem } from "./types";

const { Sider, Content } = Layout;

function KbStats() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  useEffect(() => {
    fetchDocs()
      .then(setDocs)
      .catch(() => {});
  }, []);
  const chunks = docs.reduce((sum, d) => sum + d.chunk_count, 0);
  return (
    <div style={{ padding: "0 12px" }}>
      <Card size="small" style={{ marginBottom: 8 }}>
        <Statistic title="知识库文档" value={docs.length} prefix={<FileTextOutlined />} />
      </Card>
      <Card size="small">
        <Statistic title="全库分块" value={chunks} prefix={<MessageOutlined />} />
      </Card>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<"chat" | "kb">("chat");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

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
        algorithm: theme.defaultAlgorithm,
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
              borderRight: "1px solid #e4e7ef",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
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
              <KbStats />
            )}
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
              <KbPanel />
            )}
          </Content>
        </Layout>
      </AntApp>
    </ConfigProvider>
  );
}

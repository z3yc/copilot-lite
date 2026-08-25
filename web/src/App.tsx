import { useCallback, useState } from "react";
import { fetchMessages } from "./api";
import ChatPanel from "./components/ChatPanel";
import KbPanel from "./components/KbPanel";
import SessionList from "./components/SessionList";
import type { ChatMessage } from "./types";

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
    <div className="app">
      <nav className="tab-bar">
        <button className={`tab ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>
          💬 对话
        </button>
        <button className={`tab ${tab === "kb" ? "active" : ""}`} onClick={() => setTab("kb")}>
          📚 知识库
        </button>
      </nav>

      <div className="layout">
        <SessionList activeId={sessionId} onSelect={selectSession} onNew={newSession} />
        <main className="main">
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
        </main>
      </div>
    </div>
  );
}

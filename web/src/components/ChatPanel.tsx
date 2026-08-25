import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api";
import type { ChatMessage } from "../types";

interface Props {
  sessionId: string | null;
  initialMessages: ChatMessage[];
  onSessionCreated: (id: string) => void;
  onNewSession: () => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
}

function renderMarkdown(text: string): string {
  try {
    return marked.parse(text, { async: false }) as string;
  } catch {
    return text;
  }
}

export default function ChatPanel({
  sessionId,
  initialMessages,
  onSessionCreated,
  onNewSession,
  busy,
  setBusy,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages, sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);

    // 追加用户消息 + 空助手消息
    const userMsg: ChatMessage = { role: "user", content: text };
    const assistantMsg: ChatMessage = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    let currentSid = sessionId;
    await streamChat(text, currentSid, {
      onSession: (sid) => {
        currentSid = sid;
        onSessionCreated(sid);
      },
      onChunk: (chunk) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") last.content += chunk;
          return next;
        });
      },
      onDone: () => setBusy(false),
      onError: (msg) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant" && !last.content) {
            last.content = `⚠️ ${msg}`;
          } else {
            next.push({ role: "assistant", content: `⚠️ ${msg}` });
          }
          return next;
        });
        setBusy(false);
      },
    });
  };

  return (
    <div className="chat-panel">
      <header className="chat-header">
        <span className="brand">🤖 Copilot-Lite</span>
        <button className="btn ghost" onClick={onNewSession} disabled={busy}>
          ＋ 新会话
        </button>
      </header>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty-tip">
            <p>你好！我是你的个人 AI 助理 👋</p>
            <p className="dim">
              可以让我管理待办、检索你的知识库、回答问题
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="avatar">{m.role === "user" ? "👤" : "🤖"}</div>
            <div
              className="bubble"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
            />
          </div>
        ))}
        {busy && messages.length > 0 && (
          <div className="msg assistant">
            <div className="avatar">🤖</div>
            <div className="bubble typing">▍</div>
          </div>
        )}
      </div>

      <div className="input-bar">
        <textarea
          value={input}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={1}
        />
        <button className="btn primary" onClick={send} disabled={busy || !input.trim()}>
          发送
        </button>
      </div>
    </div>
  );
}

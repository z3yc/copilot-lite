import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import { Avatar, Button, Input, Space, Typography } from "antd";
import {
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { streamChat } from "../api";
import type { ChatMessage } from "../types";

const { TextArea } = Input;
const { Text } = Typography;

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
  }, [messages, busy]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ]);

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
      <div className="chat-header">
        <Space>
          <RobotOutlined style={{ color: "#4f6ef7", fontSize: 18 }} />
          <Text strong>Copilot-Lite · 青木</Text>
        </Space>
        <Button size="small" onClick={onNewSession} disabled={busy}>
          ＋ 新会话
        </Button>
      </div>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty-tip">
            <div style={{ fontSize: 40, marginBottom: 8 }}>🤖</div>
            <Text strong style={{ fontSize: 16 }}>
              你好！我是青木，你的个人 AI 助理
            </Text>
            <div className="dim" style={{ marginTop: 4 }}>
              可以让我管理待办、检索你的知识库、回答问题
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <Avatar
              size={32}
              icon={m.role === "user" ? <UserOutlined /> : <RobotOutlined />}
              style={{
                backgroundColor: m.role === "user" ? "#4f6ef7" : "#e8ecff",
                color: m.role === "user" ? "#fff" : "#4f6ef7",
              }}
            />
            <div
              className="bubble"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
            />
          </div>
        ))}
        {busy && (
          <div className="msg assistant">
            <Avatar size={32} icon={<RobotOutlined />} style={{ backgroundColor: "#e8ecff", color: "#4f6ef7" }} />
            <div className="bubble typing">▍</div>
          </div>
        )}
      </div>

      <div className="input-bar">
        <TextArea
          value={input}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          autoSize={{ minRows: 1, maxRows: 4 }}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          disabled={busy}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={send}
          disabled={busy || !input.trim()}
        >
          发送
        </Button>
      </div>
    </div>
  );
}

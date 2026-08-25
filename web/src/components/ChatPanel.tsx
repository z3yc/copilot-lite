import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import {
  Avatar,
  Button,
  Input,
  Space,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import {
  PaperClipOutlined,
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  createSession,
  deleteSessionFile,
  fetchSessionFiles,
  streamChat,
  uploadSessionFile,
} from "../api";
import type { ChatMessage, SessionFile } from "../types";

const { TextArea } = Input;
const { Text } = Typography;

const ACCEPT =
  ".md,.txt,.pdf,.docx,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.sql,.html,.htm";

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
  const [files, setFiles] = useState<SessionFile[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages, sessionId]);

  useEffect(() => {
    if (sessionId) {
      fetchSessionFiles(sessionId)
        .then(setFiles)
        .catch(() => setFiles([]));
    } else {
      setFiles([]);
    }
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, busy]);

  // 确保存在会话（上传附件需要 session_id）
  const ensureSession = async (): Promise<string> => {
    if (sessionId) return sessionId;
    const s = await createSession();
    onSessionCreated(s.id);
    return s.id;
  };

  const onUploadFile = async (file: File) => {
    try {
      const sid = await ensureSession();
      const sf = await uploadSessionFile(sid, file);
      setFiles((prev) => [...prev, sf]);
      message.success(`已添加「${sf.filename}」到本次对话，可以提问相关内容了`);
    } catch (err) {
      message.error(`上传失败: ${err}`);
    }
  };

  const onDeleteFile = async (fileId: string) => {
    if (!sessionId) return;
    try {
      await deleteSessionFile(sessionId, fileId);
      setFiles((prev) => prev.filter((f) => f.id !== fileId));
      message.info("已移除附件");
    } catch (err) {
      message.error(`删除失败: ${err}`);
    }
  };

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

      {/* 会话附件区 */}
      {files.length > 0 && (
        <div className="file-bar">
          <span className="dim" style={{ fontSize: 12 }}>
            本次对话附件：
          </span>
          {files.map((f) => (
            <Tag
              key={f.id}
              closable
              onClose={() => onDeleteFile(f.id)}
              style={{ fontSize: 12 }}
            >
              📎 {f.filename}
            </Tag>
          ))}
        </div>
      )}

      <div className="input-bar">
        <Tooltip title="上传文件到本次对话（不进知识库），可针对文件提问">
          <Upload
            accept={ACCEPT}
            showUploadList={false}
            beforeUpload={async (file) => {
              await onUploadFile(file);
              return false;
            }}
          >
            <Button icon={<PaperClipOutlined />} disabled={busy} />
          </Upload>
        </Tooltip>
        <TextArea
          value={input}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行；或点击左侧📎上传文件到本次对话"
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

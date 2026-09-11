import { useEffect, useRef, useState } from "react";
import {
  Alert,
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
  StopOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  confirmChat,
  createSession,
  deleteSessionFile,
  fetchSessionFiles,
  streamChat,
  uploadSessionFile,
} from "../api";
import type { ChatMessage, SessionFile } from "../types";
import { renderMarkdown } from "../utils/markdown";

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
  const [confirming, setConfirming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setMessages(initialMessages);
    // 切换会话时取消进行中的流式请求（防旧会话响应写入新会话）
    abortRef.current?.abort();
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

    const controller = new AbortController();
    abortRef.current = controller;
    let currentSid = sessionId;
    try {
      await streamChat(text, currentSid, {
        signal: controller.signal,
        onSession: (sid) => {
          currentSid = sid;
          onSessionCreated(sid);
        },
        onChunk: (chunk) => {
          // 不可变更新：复制最后一条 assistant 消息再追加，
          // 避免 StrictMode 双调用 updater 时对同一对象重复追加
          setMessages((prev) => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            const last = next[lastIdx];
            if (last && last.role === "assistant") {
              next[lastIdx] = { ...last, content: last.content + chunk };
            }
            return next;
          });
        },
        onPending: (actions) => {
          // 高风险操作挂起：给最后一条助手消息附加确认信息
          setMessages((prev) => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            const last = next[lastIdx];
            if (last && last.role === "assistant") {
              next[lastIdx] = {
                ...last,
                extra: { ...(last.extra || {}), pending_confirmation: actions },
              };
            }
            return next;
          });
        },
        onDone: () => setBusy(false),
        onError: (msg) => {
          setMessages((prev) => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            const last = next[lastIdx];
            if (last && last.role === "assistant" && !last.content) {
              next[lastIdx] = { ...last, content: `⚠️ ${msg}` };
            } else {
              next.push({ role: "assistant", content: `⚠️ ${msg}` });
            }
            return next;
          });
          setBusy(false);
        },
      });
    } catch {
      // streamChat 内部已通过 onError 回调提示；这里兜底吞掉意外异常防未处理 rejection
      setBusy(false);
    } finally {
      // 无论成功/失败/中断，busy 都必须复位（防 UI 永久卡死）
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stop = () => abortRef.current?.abort();

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const pending = lastAssistant?.extra?.pending_confirmation ?? [];

  const resolvePending = async (approve: boolean) => {
    if (!sessionId || confirming) return;
    setConfirming(true);
    try {
      const res = await confirmChat(sessionId, approve);
      setMessages((prev) => [
        ...prev.map((m) =>
          m.extra?.pending_confirmation?.length
            ? { ...m, extra: { ...m.extra, pending_confirmation: [] } }
            : m
        ),
        { role: "assistant", content: res.reply },
      ]);
    } catch (err) {
      message.error(`操作失败: ${err}`);
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <Space>
          <RobotOutlined style={{ color: "var(--color-primary)", fontSize: 18 }} />
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
                backgroundColor:
                  m.role === "user" ? "var(--color-primary)" : "#e8ecff",
                color: m.role === "user" ? "#fff" : "var(--color-primary)",
              }}
            />
            <div
              className={`bubble ${m.role === "assistant" && !m.content && busy ? "typing" : ""}`}
            >
              {m.role === "assistant" && !m.content && busy ? (
                <span>▍</span>
              ) : (
                <span dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
              )}
              {m.role === "assistant" && (m.extra?.citations?.length ?? 0) > 0 && (
                <div className="citations">
                  <span className="dim" style={{ fontSize: 12 }}>
                    来源：
                  </span>
                  {m.extra!.citations!.map((c) => (
                    <a
                      key={c.index}
                      className="cite"
                      title={c.snippet || c.source}
                      onClick={(e) => {
                        e.stopPropagation();
                        message.info(`[${c.index}] ${c.source}`);
                      }}
                    >
                      [{c.index}]
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 高风险操作确认（human-in-the-loop） */}
      {pending.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ margin: "0 12px 8px" }}
          message="以下操作需要你确认后才会执行"
          description={
            <div>
              <div className="dim" style={{ fontSize: 12 }}>
                {pending.map((p) => `${p.name}(${p.arguments ?? ""})`).join("；")}
              </div>
              <Space style={{ marginTop: 8 }}>
                <Button
                  type="primary"
                  size="small"
                  loading={confirming}
                  onClick={() => resolvePending(true)}
                >
                  确认执行
                </Button>
                <Button
                  size="small"
                  disabled={confirming}
                  onClick={() => resolvePending(false)}
                >
                  取消
                </Button>
              </Space>
            </div>
          }
        />
      )}

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
        {busy ? (
          <Button danger icon={<StopOutlined />} onClick={stop}>
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={send}
            disabled={!input.trim()}
          >
            发送
          </Button>
        )}
      </div>
    </div>
  );
}

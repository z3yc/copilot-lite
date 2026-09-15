import { useCallback, useEffect, useRef, useState } from "react";
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
  ArrowDownOutlined,
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
import { ACCEPT_EXTENSIONS } from "../constants";
import type { ChatMessage, SessionFile } from "../types";
import { renderMarkdown } from "../utils/markdown";
import ModelSelect from "./ModelSelect";
import TrajectoryPanel from "./TrajectoryPanel";

const { TextArea } = Input;
const { Text } = Typography;

// 本地消息 id 生成器：为流式新增消息提供稳定 key（历史消息可能自带后端 id）
let messageSeq = 0;
const nextMessageId = () => `m-${Date.now().toString(36)}-${messageSeq++}`;

/**
 * 不可变更新「最后一条助手消息」（不存在则原样返回）。
 *
 * 统一的理由是 StrictMode 会双调用 updater：任何一处改成原地修改都会出重复内容，
 * 机制集中在这里，调用点不可能各自写歪（AGENTS §5 异步 UI 铁律）。
 */
function updateLastAssistant(
  prev: ChatMessage[],
  patch: (last: ChatMessage) => Partial<ChatMessage>
): ChatMessage[] {
  const next = [...prev];
  const lastIdx = next.length - 1;
  const last = next[lastIdx];
  if (last && last.role === "assistant") {
    next[lastIdx] = { ...last, ...patch(last) };
  }
  return next;
}

interface Props {
  sessionId: string | null;
  /** 当前会话标题；为空时回退到品牌名 */
  sessionTitle?: string | null;
  initialMessages: ChatMessage[];
  onSessionCreated: (id: string) => void;
  onNewSession: () => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
  /** 未配置模型时，引导前往「个人主页 → 模型设置」 */
  onOpenSettings?: () => void;
}

export default function ChatPanel({
  sessionId,
  sessionTitle,
  initialMessages,
  onSessionCreated,
  onNewSession,
  busy,
  setBusy,
  onOpenSettings,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<SessionFile[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // 是否有流在飞：显式标记，避免用可空的 sessionId/abortRef 去推断「是否有流」
  const streamingRef = useRef(false);
  // 进行中的流属于哪个会话：用于区分「新建会话（null→id）」与「真的切走了」
  const streamSessionRef = useRef<string | null>(null);
  // 是否因「会话切换/新建会话」而中止：用于区分「停止按钮」与「切换自动中止」，
  // 后者不得在刚被清空的列表里留下「生成出错」气泡
  const abortedBySwitchRef = useRef(false);

  useEffect(() => {
    // 新会话（sessionId 仍为 null）时父组件把消息换新（App.newSession 会 setMessages([])）
    // = 点了 SessionList 的「新建会话」：此时 sessionId 没有变化、下面的切换 effect 不会触发，
    // 必须在这里取消进行中的流，否则它的 chunk 会写进刚被清空的消息列表。
    if (streamingRef.current && sessionId === null) {
      abortedBySwitchRef.current = true;
      abortRef.current?.abort();
    }
    setMessages(initialMessages);
    // 只随 initialMessages 变化重跑；sessionId 在此读取当前渲染值即可（切换会话由下面的 effect 处理）。
  }, [initialMessages]);

  useEffect(() => {
    // 仅在真正切换到别的会话时取消进行中的流（防旧会话响应写入新会话）；
    // 新会话首条消息会经历 null→新 id，那不算切换，取消它 = 自己杀自己。
    if (streamingRef.current && sessionId !== streamSessionRef.current) {
      abortedBySwitchRef.current = true;
      abortRef.current?.abort();
    }
  }, [sessionId]);

  useEffect(() => {
    if (sessionId) {
      fetchSessionFiles(sessionId)
        .then(setFiles)
        .catch(() => setFiles([]));
    } else {
      setFiles([]);
    }
  }, [sessionId]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  // 仅在用户停留底部时自动跟随，避免上翻阅读历史时被新 chunk 强行拽回
  useEffect(() => {
    if (atBottom) scrollToBottom();
  }, [messages, busy, atBottom, scrollToBottom]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

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
    abortedBySwitchRef.current = false; // 新一轮请求开始，清掉上一轮的中止来源标记
    setMessages((prev) => [
      ...prev,
      { id: nextMessageId(), role: "user", content: text },
      { id: nextMessageId(), role: "assistant", content: "" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    streamingRef.current = true;            // 有流在飞（不依赖可空 id 推断）
    streamSessionRef.current = sessionId;   // 本轮流属于哪个会话
    let currentSid = sessionId;
    try {
      await streamChat(text, currentSid, {
        signal: controller.signal,
        onSession: (sid) => {
          currentSid = sid;
          streamSessionRef.current = sid;   // 新会话建出来了，归属随之更新
          onSessionCreated(sid);
        },
        onChunk: (chunk) => {
          // 不可变更新：复制最后一条 assistant 消息再追加，
          // 避免 StrictMode 双调用 updater 时对同一对象重复追加
          setMessages((prev) =>
            updateLastAssistant(prev, (last) => ({ content: last.content + chunk }))
          );
        },
        onPending: (actions) => {
          // 高风险操作挂起：给最后一条助手消息附加确认信息
          setMessages((prev) =>
            updateLastAssistant(prev, (last) => ({
              extra: { ...(last.extra || {}), pending_confirmation: actions },
            }))
          );
        },
        onDone: (payload) => {
          // 轨迹落库随 done 一并到达（旧后端不带）：合并到最后一条助手消息
          if (payload?.trajectory) {
            setMessages((prev) =>
              updateLastAssistant(prev, (last) => ({
                extra: { ...(last.extra || {}), trajectory: payload.trajectory },
              }))
            );
          }
          setBusy(false);
        },
        onError: (msg) => {
          // 因会话切换/新建会话而中止：列表刚被清空，不应留下错误气泡
          if (abortedBySwitchRef.current) {
            setBusy(false);
            return;
          }
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && !last.content) {
              return updateLastAssistant(prev, () => ({
                content: `生成出错：${msg}`,
              }));
            }
            return [...prev, { role: "assistant", content: `生成出错：${msg}` }];
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
      streamingRef.current = false;
      streamSessionRef.current = null;
      abortedBySwitchRef.current = false;
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
          <Text
            strong
            ellipsis
            style={{ maxWidth: 360 }}
            title={sessionTitle || undefined}
          >
            {sessionTitle || "Copilot-Lite · 青木"}
          </Text>
        </Space>
        <Space size={8}>
          <ModelSelect onOpenSettings={onOpenSettings} />
          <Button size="small" onClick={onNewSession} disabled={busy}>
            ＋ 新会话
          </Button>
        </Space>
      </div>

      <div className="messages" ref={scrollRef} onScroll={handleScroll}>
        {messages.length === 0 && (
          <div className="empty-tip">
            <div style={{ marginBottom: 8 }}>
              <RobotOutlined style={{ fontSize: 40, color: "var(--color-primary)" }} />
            </div>
            <Text strong style={{ fontSize: 16 }}>
              你好！我是青木，你的个人 AI 助理
            </Text>
            <div className="dim" style={{ marginTop: 4 }}>
              可以让我管理待办、检索你的知识库、回答问题
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={m.id ?? i} className={`msg ${m.role}`}>
            <Avatar
              size={32}
              icon={m.role === "user" ? <UserOutlined /> : <RobotOutlined />}
              style={{
                backgroundColor:
                  m.role === "user"
                    ? "var(--color-primary)"
                    : "var(--color-primary-soft)",
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
                      role="button"
                      tabIndex={0}
                      aria-label={`查看来源 ${c.index}`}
                      title={c.snippet || c.source}
                      onClick={(e) => {
                        e.stopPropagation();
                        message.info(`[${c.index}] ${c.source}`);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          message.info(`[${c.index}] ${c.source}`);
                        }
                      }}
                    >
                      [{c.index}]
                    </a>
                  ))}
                </div>
              )}
              {m.role === "assistant" && m.extra?.trajectory && (
                <TrajectoryPanel trajectory={m.extra.trajectory} />
              )}
            </div>
          </div>
        ))}
      </div>

      {!atBottom && (
        <Tooltip title="回到底部">
          <Button
            className="scroll-bottom-btn"
            shape="circle"
            aria-label="回到底部"
            icon={<ArrowDownOutlined />}
            onClick={scrollToBottom}
          />
        </Tooltip>
      )}

      {/* 高风险操作确认（human-in-the-loop） */}
      {pending.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ margin: "0 12px 8px" }}
          title="以下操作需要你确认后才会执行"
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
              <PaperClipOutlined /> {f.filename}
            </Tag>
          ))}
        </div>
      )}

      <div className="input-bar">
        <Tooltip title="上传文件到本次对话（不进知识库），可针对文件提问">
          <Upload
            accept={ACCEPT_EXTENSIONS}
            showUploadList={false}
            beforeUpload={async (file) => {
              await onUploadFile(file);
              return false;
            }}
          >
            <Button
              icon={<PaperClipOutlined />}
              aria-label="上传附件到本次对话"
              disabled={busy}
            />
          </Upload>
        </Tooltip>
        <TextArea
          value={input}
          placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
          autoSize={{ minRows: 1, maxRows: 4 }}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
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

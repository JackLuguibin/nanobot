import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { useAppStore } from "../store";
import { registerChatHandler, getWSRef } from "../hooks/useWebSocket";
import * as api from "../api/client";
import { Button, Tag, Tooltip, Popconfirm } from "antd";
import {
  PlusOutlined,
  LoadingOutlined,
  CopyOutlined,
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { Bot, User, MessageSquare, X, Wand2, Square } from "lucide-react";
import type { StreamChunk } from "../api/types";
import type { TextAreaRef } from "antd/es/input/TextArea";
import Input from "antd/es/input";
import { SubagentPanel, type SubagentTask } from "../components/SubagentPanel";

interface ChatInputProps {
  inputRef: React.RefObject<TextAreaRef | null>;
  value: string;
  onChange: (value: string) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
}

function ChatInput({
  inputRef,
  value,
  onChange,
  onKeyDown,
  onSend,
  onStop,
  isStreaming,
}: ChatInputProps) {
  const [focused, setFocused] = useState(false);
  const canSend = value.trim().length > 0;

  return (
    <div className="space-y-2">
      <div
        className={`relative rounded-2xl border transition-all duration-200 bg-white dark:bg-gray-900 ${
          focused
            ? "border-blue-400 dark:border-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.15)]"
            : "border-gray-200 dark:border-gray-700 shadow-sm hover:border-gray-300 dark:hover:border-gray-600"
        }`}
      >
        <Input.TextArea
          ref={inputRef as React.RefObject<TextAreaRef>}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Send a message..."
          autoSize={{ minRows: 1, maxRows: 8 }}
          variant="borderless"
          className="!text-[15px] !leading-relaxed !py-3.5 !px-4 !pr-14 resize-none bg-transparent"
          style={{ boxShadow: "none" }}
        />

        {/* Action bar */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-0">
          <span className="text-xs text-gray-400 dark:text-gray-500 select-none">
            {isStreaming ? (
              <span className="flex items-center gap-1.5 text-blue-500">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                Generating…
              </span>
            ) : (
              <span>Enter to send · Shift+Enter for new line</span>
            )}
          </span>

          <button
            onClick={isStreaming ? onStop : onSend}
            disabled={!isStreaming && !canSend}
            className={`flex items-center justify-center w-8 h-8 rounded-xl transition-all duration-150 ${
              isStreaming
                ? "bg-red-500 hover:bg-red-600 text-white shadow-md shadow-red-500/30 hover:shadow-red-500/40 hover:scale-105"
                : canSend
                  ? "bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/30 hover:shadow-blue-500/40 hover:scale-105"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed"
            }`}
            title={isStreaming ? "Stop generating" : "Send message"}
          >
            {isStreaming ? (
              <Square className="w-3.5 h-3.5 fill-current" />
            ) : (
              <svg
                viewBox="0 0 16 16"
                className="w-3.5 h-3.5 fill-current"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path d="M.5 1.163A1 1 0 0 1 1.97.28l12.868 6.837a1 1 0 0 1 0 1.766L1.969 15.72A1 1 0 0 1 .5 14.836V10.33a1 1 0 0 1 .816-.983L8.5 8 1.316 6.653A1 1 0 0 1 .5 5.67V1.163Z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_call_id?: string;
  tool_name?: string;
  isStreaming?: boolean;
  /** 发送时间，ISO 字符串，用于展示 */
  created_at?: string;
  timestamp?: string;
  /** 消息来源：user / main_agent / sub_agent / tool_call；聊天区仅展示 user 与 main_agent */
  source?: "user" | "main_agent" | "sub_agent" | "tool_call";
}

interface ToolCall {
  id: string;
  name: string;
  args: string;
  status: "pending" | "running" | "success" | "error";
  result?: string;
}

/** 将 Agent 的 tool_hint 拆成多行，避免 read_file("a")read_file("b") 挤在一行 */
function formatToolHintMultiline(hint: string): string {
  return hint.replace(/\),\s*(?=[A-Za-z_]\w*\()/g, ")\n");
}

export default function Chat() {
  const { sessionKey: paramSessionKey } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentSessionKey, setCurrentSessionKey, currentBotId, addToast } =
    useAppStore();

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [sessionsSidebarOpen, setSessionsSidebarOpen] = useState(false);
  const [sessionsSidebarCollapsed, setSessionsSidebarCollapsed] =
    useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  /** 流式过程中后端单独下发的工具调用摘要（与正文 Markdown 分离） */
  const [streamingToolProgress, setStreamingToolProgress] = useState<string[]>(
    [],
  );
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [subagentTasks, setSubagentTasks] = useState<SubagentTask[]>([]);
  const [subagentPanelOpen, setSubagentPanelOpen] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<TextAreaRef>(null);
  const streamingContentRef = useRef("");

  const activeSessionKey = paramSessionKey || currentSessionKey;

  const { data: sessions } = useQuery({
    queryKey: ["sessions", currentBotId],
    queryFn: () => api.listSessions(currentBotId),
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (key: string) => api.deleteSession(key, currentBotId),
    onSuccess: (_, key) => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session", key] });
      if (activeSessionKey === key) {
        setCurrentSessionKey(null);
        setMessages([]);
        setShowSuggestions(true);
        setSubagentTasks([]);
        navigate("/chat");
        setSessionsSidebarOpen(false);
      }
      addToast({ type: "success", message: "会话已删除" });
    },
    onError: () => {
      addToast({ type: "error", message: "删除会话失败" });
    },
  });

  const { data: sessionData } = useQuery({
    queryKey: ["session", activeSessionKey, currentBotId],
    queryFn: () => api.getSession(activeSessionKey!, currentBotId),
    enabled: !!activeSessionKey,
  });

  // 仅在用户主动切换会话时清空消息；从「无会话」到「新会话」(首条消息后拿到 session_key) 时保留当前消息
  const prevActiveSessionKeyRef = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const prev = prevActiveSessionKeyRef.current;
    const isSwitch =
      prev != null && activeSessionKey != null && prev !== activeSessionKey;
    if (isSwitch) {
      setMessages([]);
    }
    setShowSuggestions(!activeSessionKey);
    prevActiveSessionKeyRef.current = activeSessionKey;
  }, [activeSessionKey]);

  useEffect(() => {
    if (sessionData?.messages && !isStreaming) {
      const serverMessages = sessionData.messages as Message[];
      setMessages((prev) => {
        // If local has more messages (e.g. assistant msg just added in chat_done), don't overwrite with old sessionData
        if (prev.length > serverMessages.length) return prev;
        return serverMessages.map((msg, idx) => ({
          ...msg,
          id: `msg-${idx}-${Date.now()}`,
        }));
      });
      setShowSuggestions(false);
    } else if (sessionData?.messages && isStreaming) {
      // Stream just started and getSession returned a session (user message is already in it).
      // Load those messages so the user message appears immediately.
      const serverMessages = sessionData.messages as Message[];
      setMessages((prev) => {
        if (prev.length > 0) return prev;
        return serverMessages.map((msg, idx) => ({
          ...msg,
          id: `msg-${idx}-${Date.now()}`,
        }));
      });
    } else if (!activeSessionKey) {
      setShowSuggestions(true);
    }
  }, [sessionData, activeSessionKey, isStreaming]);

  // Refresh session list when current session data loads/updates so sidebar message count stays in sync
  const sessionMessageCount = sessionData?.message_count;
  useEffect(() => {
    if (activeSessionKey && sessionMessageCount !== undefined) {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }, [activeSessionKey, sessionMessageCount, queryClient]);

  /** 聊天区只展示用户与主 Agent 消息，过滤掉子 Agent 与工具调用。不排序，沿用后端返回的时序（最新在下方）。 */
  const displayMessages = useMemo(() => {
    return messages.filter(
      (m) => m.source !== "sub_agent" && m.source !== "tool_call",
    );
  }, [messages]);

  // 仅有一条消息时保持滚动在顶部，避免第一条用户消息被滚出视口；多条消息时滚到底部
  useEffect(() => {
    const container = messagesContainerRef.current;
    const endEl = messagesEndRef.current;
    if (!container) return;
    if (displayMessages.length <= 1) {
      container.scrollTop = 0;
      return;
    }
    endEl?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages.length, streamingContent, streamingToolProgress.length]);

  const handleStreamChunk = useCallback(
    (chunk: StreamChunk) => {
      if (chunk.type === "session_key" && chunk.session_key) {
        setCurrentSessionKey(chunk.session_key);
        navigate(`/chat/${chunk.session_key}`, { replace: true });
        queryClient.invalidateQueries({ queryKey: ["sessions"] });
      } else if (chunk.type === "chat_token" && chunk.content) {
        streamingContentRef.current += chunk.content;
        setStreamingContent((prev) => prev + chunk.content);
      } else if (chunk.type === "tool_progress" && chunk.content) {
        setStreamingToolProgress((prev) => [...prev, chunk.content as string]);
      } else if (chunk.type === "tool_call" && chunk.tool_call) {
        const tc = chunk.tool_call;
        setToolCalls((prev) => [
          ...prev,
          {
            id: tc.id,
            name: tc.name,
            args: JSON.stringify(tc.arguments, null, 2),
            status: "running",
          },
        ]);
      } else if (chunk.type === "tool_result" && chunk.tool_name) {
        setToolCalls((prev) =>
          prev.map((tc) =>
            tc.name === chunk.tool_name
              ? { ...tc, status: "success", result: chunk.tool_result }
              : tc,
          ),
        );
      } else if (chunk.type === "error" && chunk.error) {
        setStreamingToolProgress([]);
        setToolCalls((prev) =>
          prev.map((tc) => ({ ...tc, status: "error", result: chunk.error })),
        );
        addToast({ type: "error", message: chunk.error });
      } else if (
        chunk.type === "subagent_start" &&
        chunk.subagent_id &&
        chunk.label
      ) {
        // Subagent started - add to panel
        const subagentId = chunk.subagent_id;
        const subagentLabel = chunk.label;
        setSubagentTasks((prev) => [
          ...prev,
          {
            id: subagentId,
            label: subagentLabel,
            task: chunk.task,
            status: "running",
          },
        ]);
        setSubagentPanelOpen(true);
      } else if (chunk.type === "assistant_message" && chunk.content) {
        const assistantContent = chunk.content;
        setMessages((prev) => [
          ...prev,
          {
            id: `msg-${Date.now()}-${Math.random()}`,
            role: "assistant",
            content: assistantContent,
            created_at: new Date().toISOString(),
            source: chunk.source ?? "main_agent",
          },
        ]);
      } else if (chunk.type === "subagent_done" && chunk.subagent_id) {
        // Subagent completed - update status
        setSubagentTasks((prev) =>
          prev.map((task) =>
            task.id === chunk.subagent_id
              ? {
                  ...task,
                  status: chunk.status === "ok" ? "success" : "error",
                  result: chunk.result,
                }
              : task,
          ),
        );
      } else if (chunk.type === "chat_done") {
        // Prefer content from chat_done (backend sends full response when no tokens were streamed)
        const finalContent =
          (chunk.content !== undefined && chunk.content !== ""
            ? chunk.content
            : streamingContentRef.current) || "Task completed.";
        streamingContentRef.current = "";
        setIsStreaming(false);
        setStreamingContent("");
        setStreamingToolProgress([]);
        const assistantMsg: Message = {
          id: `msg-${Date.now()}`,
          role: "assistant",
          content: finalContent,
          created_at: new Date().toISOString(),
          source: chunk.source ?? "main_agent",
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setToolCalls([]);
        queryClient.invalidateQueries({ queryKey: ["sessions"] });
        // Update the session cache so sessionData stays in sync with the latest session.
        // Functional form reads current cache at call time, avoiding stale closure values.
        queryClient.setQueryData(
          ["session", activeSessionKey, currentBotId],
          (old: typeof sessionData | undefined) => {
            if (!old) return old;
            return {
              ...old,
              messages: [...(old.messages ?? []), assistantMsg],
              message_count: (old.message_count ?? 0) + 1,
            };
          },
        );
      }
    },
    [addToast, queryClient, navigate, setCurrentSessionKey, activeSessionKey, currentBotId],
  );

  // Register WebSocket chat message handler (WS streaming replaces SSE)
  useEffect(() => {
    const unregister = registerChatHandler(handleStreamChunk);
    return unregister;
  }, [handleStreamChunk]);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;

    const userMessage = input.trim();
    setInput("");
    setShowSuggestions(false);

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: userMessage,
        created_at: new Date().toISOString(),
        source: "user",
      },
    ]);

    setIsStreaming(true);
    setStreamingContent("");
    streamingContentRef.current = "";
    setToolCalls([]);
    setStreamingToolProgress([]);

    const ws = getWSRef()?.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setIsStreaming(false);
      setStreamingContent("");
      addToast({ type: "error", message: "WebSocket not connected" });
      return;
    }

    ws.send(JSON.stringify({
      type: "chat",
      message: userMessage,
      session_key: activeSessionKey || undefined,
      bot_id: currentBotId || undefined,
    }));
  };

  const handleStop = () => {
    // Agent interruption is not yet supported via WebSocket.
    // Stop button clears local streaming state only.
    setIsStreaming(false);
    setStreamingContent("");
    setToolCalls([]);
    setStreamingToolProgress([]);
    addToast({ type: "info", message: "Generation stopped" });
  };

  const handleNewChat = () => {
    setCurrentSessionKey(null);
    setMessages([]);
    setShowSuggestions(true);
    setSubagentTasks([]);
    navigate("/chat");
    inputRef.current?.focus();
    setSessionsSidebarOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSelectSession = (sessionKey: string) => {
    setCurrentSessionKey(sessionKey);
    navigate(`/chat/${sessionKey}`);
    setSessionsSidebarOpen(false);
  };

  const copyMessage = async (content: string, id: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(id);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch {
      addToast({ type: "error", message: "Failed to copy" });
    }
  };

  const suggestions = [
    {
      text: "Review the code structure of the current repository.",
      label: "Review code structure",
    },
    {
      text: "What automation options can be integrated?",
      label: "View automation options",
    },
    { text: "Write a simple Python script for me", label: "Write a script" },
  ];

  const toolCallTagColor = (status: ToolCall["status"]) => {
    if (status === "running") return "processing";
    if (status === "success") return "success";
    return "error";
  };

  /** 格式化消息时间：年月日 + 时:分:秒 */
  const formatMessageTime = (isoStr: string | undefined): string => {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      const dateStr = d.toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
      const timeStr = d.toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
      return `${dateStr} ${timeStr}`;
    } catch {
      return "";
    }
  };

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden overflow-x-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 relative">
      {/* Mobile Sessions Toggle Button */}
      <button
        onClick={() => setSessionsSidebarOpen(!sessionsSidebarOpen)}
        className="md:hidden fixed bottom-20 right-4 z-30 p-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-full shadow-lg shadow-primary-500/30 hover:shadow-xl hover:scale-105 transition-all"
      >
        {sessionsSidebarOpen ? (
          <X className="w-5 h-5" />
        ) : (
          <MessageSquare className="w-5 h-5" />
        )}
      </button>

      {/* Sessions Sidebar */}
      <div
        className={`
          ${sessionsSidebarOpen ? "translate-x-0" : "-translate-x-full"}
          ${sessionsSidebarCollapsed ? "md:-translate-x-full md:w-0 md:pointer-events-none md:overflow-hidden" : "md:translate-x-0 md:w-64"}
          fixed md:relative z-20 h-screen md:h-full
          w-64 bg-white/80 dark:bg-gray-800/80 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-700/50
          flex flex-col transition-transform duration-300 ease-out
        `}
      >
        <div className="flex-1 overflow-y-auto no-scrollbar p-3 space-y-2">
          {sessions?.map((session) => (
            <div
              key={session.key}
              className={`flex items-stretch rounded-xl transition-all ${
                activeSessionKey === session.key
                  ? "bg-gradient-to-r from-primary-50 to-blue-50 dark:from-primary-900/30 dark:to-blue-900/20 text-primary-700 dark:text-primary-300"
                  : "hover:bg-gray-100 dark:hover:bg-gray-700/50"
              }`}
            >
              <button
                type="button"
                onClick={() => handleSelectSession(session.key)}
                className="flex-1 min-w-0 text-left px-4 py-3 rounded-l-xl"
              >
                <span className="text-sm font-medium truncate block">
                  {session.title || session.key}
                </span>
                <span className="text-xs text-gray-500 mt-1 block">
                  {session.message_count} messages
                </span>
                {session.created_at && (
                  <span className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 block">
                    {formatMessageTime(session.created_at)}
                  </span>
                )}
              </button>
              <Popconfirm
                title="删除会话"
                description={`确定删除「${session.title || session.key}」？`}
                onConfirm={() => deleteSessionMutation.mutate(session.key)}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <button
                  type="button"
                  onClick={(e) => e.stopPropagation()}
                  title="删除会话"
                  className="self-center shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:text-gray-500 dark:hover:text-red-400 dark:hover:bg-red-500/10 transition-colors duration-150 mr-1"
                >
                  <DeleteOutlined className="text-sm" />
                </button>
              </Popconfirm>
            </div>
          ))}
        </div>
      </div>

      {/* Mobile Overlay */}
      {sessionsSidebarOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-10 backdrop-blur-sm"
          onClick={() => setSessionsSidebarOpen(false)}
        />
      )}

      {sessionsSidebarCollapsed && (
        <Button
          type="text"
          icon={<MenuUnfoldOutlined />}
          onClick={() => setSessionsSidebarCollapsed(false)}
          className="hidden md:flex absolute left-2 top-20 z-30 text-gray-500 hover:text-primary-500 bg-white/80 dark:bg-gray-900/80 rounded-full shadow"
          title="展开会话"
        />
      )}

      {/* Chat Area */}
      <div className="flex-1 flex min-w-0 min-h-0">
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {/* Header */}
          <div className="h-12 px-6 flex items-center justify-between border-b border-gray-200/50 dark:border-gray-700/50 bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary-500/20">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">Chat</h2>
                <p className="text-xs text-gray-500">Work with Nanobot</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="text"
                icon={
                  sessionsSidebarCollapsed ? (
                    <MenuUnfoldOutlined />
                  ) : (
                    <MenuFoldOutlined />
                  )
                }
                onClick={() => setSessionsSidebarCollapsed((prev) => !prev)}
                className="!px-2 !py-1"
                title={
                  sessionsSidebarCollapsed ? "展开会话列表" : "收起会话列表"
                }
              />
              {sessions && sessions.length > 0 && (
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={handleNewChat}
                  className="hidden md:flex"
                >
                  New Chat
                </Button>
              )}
            </div>
          </div>

          {/* Messages / Hero */}
          <div
            ref={messagesContainerRef}
            className="flex-1 min-h-0 overflow-y-auto no-scrollbar px-4 md:px-6 py-2 md:py-3"
          >
            {displayMessages.length === 0 && showSuggestions ? (
              <div className="min-h-full flex flex-col items-center justify-start pt-2 md:pt-4 text-center text-gray-600 dark:text-gray-300">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-100 to-blue-100 dark:from-primary-900/30 dark:to-blue-900/20 flex items-center justify-center mb-6 shadow-xl shadow-primary-500/10">
                  <Bot className="w-10 h-10 text-primary-600" />
                </div>
                <h3 className="text-2xl font-bold mb-3 bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
                  Hello, how can I help you today?
                </h3>
                <p className="text-sm text-gray-500 mb-8 max-w-md">
                  Ask anything about your projects, code, or environment.
                  I&apos;ll use your Nanobot setup to help.
                </p>
                <div className="grid gap-3 w-full max-w-xl">
                  {suggestions.map((suggestion, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setInput(suggestion.text);
                        inputRef.current?.focus();
                      }}
                      className="flex items-center justify-between px-5 py-4 rounded-xl bg-white dark:bg-gray-800 shadow-sm hover:shadow-lg border border-gray-100 dark:border-gray-700 text-left text-sm hover:scale-[1.02] transition-all group"
                    >
                      <div className="flex items-center gap-3">
                        <Wand2 className="w-4 h-4 text-primary-500" />
                        <span className="font-medium">{suggestion.label}</span>
                      </div>
                      <span className="text-gray-400 group-hover:translate-x-1 transition-transform">
                        →
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-4 max-w-3xl mx-auto">
                {displayMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex gap-3 overflow-visible ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                  >
                    <div
                      className={`w-10 h-10 min-w-[2.5rem] min-h-[2.5rem] rounded-xl flex items-center justify-center flex-shrink-0 overflow-visible p-1.5 box-border ${
                        msg.role === "user"
                          ? "bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary-500/25"
                          : "bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-600"
                      }`}
                    >
                      {msg.role === "user" ? (
                        <User
                          className="w-5 h-5 min-w-5 min-h-5 text-white flex-shrink-0"
                          strokeWidth={2}
                        />
                      ) : (
                        <Bot className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                      )}
                    </div>
                    <div
                      className={`relative rounded-2xl px-5 py-4 max-w-[85%] min-w-0 group/bubble ${
                        msg.role === "user"
                          ? "min-w-[8rem] bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-md shadow-primary-500/20 rounded-br-md"
                          : "bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 shadow-sm rounded-bl-md"
                      }`}
                    >
                      <Tooltip title="Copy" placement="top">
                        <Button
                          type="text"
                          size="small"
                          icon={
                            copiedMessageId === msg.id ? (
                              <CheckOutlined className="text-green-500" />
                            ) : (
                              <CopyOutlined
                                className={
                                  msg.role === "user"
                                    ? "text-white/70"
                                    : "text-gray-400"
                                }
                              />
                            )
                          }
                          className="absolute top-2 right-2 opacity-0 group-hover/bubble:opacity-100 hover:!opacity-100 transition-opacity !p-1 !h-7 !w-7"
                          onClick={() => copyMessage(msg.content, msg.id)}
                        />
                      </Tooltip>
                      <div
                        className={`prose prose-sm dark:prose-invert max-w-none pr-8 ${msg.role === "user" ? "prose-invert" : ""}`}
                      >
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                      {(msg.created_at ?? msg.timestamp) && (
                        <div
                          className={`mt-2 text-xs ${
                            msg.role === "user"
                              ? "text-white/70"
                              : "text-gray-400 dark:text-gray-500"
                          }`}
                        >
                          {formatMessageTime(msg.created_at ?? msg.timestamp)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Streaming content */}
                {isStreaming &&
                  (streamingContent || streamingToolProgress.length > 0) && (
                    <>
                      <div className="flex gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-600 flex items-center justify-center shrink-0">
                          <Bot className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                        </div>
                        <div className="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl px-5 py-4 shadow-sm min-w-0 flex-1 max-w-[85%]">
                          {streamingContent ? (
                            <div className="prose prose-sm dark:prose-invert max-w-none">
                              <ReactMarkdown>{streamingContent}</ReactMarkdown>
                            </div>
                          ) : null}
                          {streamingToolProgress.length > 0 ? (
                            <div
                              className={
                                streamingContent
                                  ? "mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 space-y-2"
                                  : "space-y-2"
                              }
                            >
                              <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
                                <ToolOutlined className="text-blue-500" />
                                <span>工具调用</span>
                              </div>
                              {streamingToolProgress.map((hint, idx) => (
                                <pre
                                  key={`${idx}-${hint.slice(0, 24)}`}
                                  className="text-xs leading-relaxed font-mono text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-900/90 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2.5 whitespace-pre-wrap break-all m-0 overflow-x-auto"
                                >
                                  {formatToolHintMultiline(hint)}
                                </pre>
                              ))}
                            </div>
                          ) : null}
                          <LoadingOutlined className="mt-2 text-primary-500" />
                        </div>
                      </div>

                      {/* Tool calls */}
                      {toolCalls.length > 0 && (
                        <div className="ml-12 space-y-2">
                          {toolCalls.map((tc) => (
                            <div
                              key={tc.id}
                              className={`rounded-xl p-4 border ${
                                tc.status === "running"
                                  ? "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800"
                                  : tc.status === "success"
                                    ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
                                    : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800"
                              }`}
                            >
                              <div className="flex items-center gap-2 mb-2">
                                {tc.status === "running" ? (
                                  <LoadingOutlined className="text-blue-500" />
                                ) : tc.status === "success" ? (
                                  <CheckOutlined className="text-green-500" />
                                ) : (
                                  <CloseOutlined className="text-red-500" />
                                )}
                                <span className="font-medium text-sm">
                                  {tc.name}
                                </span>
                                <Tag color={toolCallTagColor(tc.status)}>
                                  {tc.status}
                                </Tag>
                              </div>
                              {tc.args && (
                                <pre className="text-xs bg-gray-900 text-gray-100 p-2 rounded-lg overflow-x-auto">
                                  {tc.args}
                                </pre>
                              )}
                              {tc.result && (
                                <pre className="text-xs mt-2 bg-gray-900 text-gray-100 p-2 rounded-lg overflow-x-auto max-h-32">
                                  {tc.result.slice(0, 500)}
                                  {tc.result.length > 500 && "..."}
                                </pre>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input */}
          <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-xl pb-safe">
            <div className="max-w-3xl mx-auto px-4 py-4">
              <ChatInput
                inputRef={inputRef}
                value={input}
                onChange={setInput}
                onKeyDown={handleKeyDown}
                onSend={handleSend}
                onStop={handleStop}
                isStreaming={isStreaming}
              />
            </div>
          </div>
        </div>

        {/* Subagent Panel */}
        {subagentTasks.length > 0 && (
          <SubagentPanel
            tasks={subagentTasks}
            collapsed={!subagentPanelOpen}
            onCollapse={() => setSubagentPanelOpen(false)}
          />
        )}
      </div>
    </div>
  );
}

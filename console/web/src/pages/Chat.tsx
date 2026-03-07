import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { useAppStore } from '../store';
import * as api from '../api/client';
import { Button, Tag, Tooltip } from 'antd';
import {
  PlusOutlined,
  LoadingOutlined,
  CopyOutlined,
  CheckOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { Bot, User, MessageSquare, X, Wand2, Square } from 'lucide-react';
import type { StreamChunk } from '../api/types';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import Input from 'antd/es/input';

interface ChatInputProps {
  inputRef: React.RefObject<TextAreaRef | null>;
  value: string;
  onChange: (value: string) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
}

function ChatInput({ inputRef, value, onChange, onKeyDown, onSend, onStop, isStreaming }: ChatInputProps) {
  const [focused, setFocused] = useState(false);
  const canSend = value.trim().length > 0;

  return (
    <div className="space-y-2">
      <div
        className={`relative rounded-2xl border transition-all duration-200 bg-white dark:bg-gray-900 ${
          focused
            ? 'border-blue-400 dark:border-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.15)]'
            : 'border-gray-200 dark:border-gray-700 shadow-sm hover:border-gray-300 dark:hover:border-gray-600'
        }`}
      >
        <Input.TextArea
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="发送消息..."
          autoSize={{ minRows: 1, maxRows: 8 }}
          variant="borderless"
          className="!text-[15px] !leading-relaxed !py-3.5 !px-4 !pr-14 resize-none bg-transparent"
          style={{ boxShadow: 'none' }}
        />

        {/* Action bar */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-0">
          <span className="text-xs text-gray-400 dark:text-gray-500 select-none">
            {isStreaming ? (
              <span className="flex items-center gap-1.5 text-blue-500">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                正在生成…
              </span>
            ) : (
              <span>Enter 发送 · Shift+Enter 换行</span>
            )}
          </span>

          <button
            onClick={isStreaming ? onStop : onSend}
            disabled={!isStreaming && !canSend}
            className={`flex items-center justify-center w-8 h-8 rounded-xl transition-all duration-150 ${
              isStreaming
                ? 'bg-red-500 hover:bg-red-600 text-white shadow-md shadow-red-500/30 hover:shadow-red-500/40 hover:scale-105'
                : canSend
                ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/30 hover:shadow-blue-500/40 hover:scale-105'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
            }`}
            title={isStreaming ? '停止生成' : '发送消息'}
          >
            {isStreaming ? (
              <Square className="w-3.5 h-3.5 fill-current" />
            ) : (
              <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 fill-current" xmlns="http://www.w3.org/2000/svg">
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
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_call_id?: string;
  tool_name?: string;
  isStreaming?: boolean;
}

interface ToolCall {
  id: string;
  name: string;
  args: string;
  status: 'pending' | 'running' | 'success' | 'error';
  result?: string;
}

export default function Chat() {
  const { sessionKey: paramSessionKey } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentSessionKey, setCurrentSessionKey, addToast } = useAppStore();

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [sessionsSidebarOpen, setSessionsSidebarOpen] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<TextAreaRef>(null);
  const streamingContentRef = useRef('');

  const activeSessionKey = paramSessionKey || currentSessionKey;

  const { data: sessions } = useQuery({
    queryKey: ['sessions'],
    queryFn: api.listSessions,
  });

  const { data: sessionData } = useQuery({
    queryKey: ['session', activeSessionKey],
    queryFn: () => api.getSession(activeSessionKey!),
    enabled: !!activeSessionKey,
  });

  useEffect(() => {
    if (sessionData?.messages && !isStreaming) {
      setMessages(
        (sessionData.messages as Message[]).map((msg, idx) => ({
          ...msg,
          id: `msg-${idx}-${Date.now()}`,
        }))
      );
      setShowSuggestions(false);
    } else if (!activeSessionKey) {
      setShowSuggestions(true);
    }
  }, [sessionData, activeSessionKey, isStreaming]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleStreamChunk = useCallback(
    (chunk: StreamChunk) => {
      if (chunk.type === 'session_key' && chunk.session_key) {
        setCurrentSessionKey(chunk.session_key);
        navigate(`/chat/${chunk.session_key}`, { replace: true });
      } else if (chunk.type === 'chat_token' && chunk.content) {
        streamingContentRef.current += chunk.content;
        setStreamingContent((prev) => prev + chunk.content);
      } else if (chunk.type === 'tool_call' && chunk.tool_call) {
        const tc = chunk.tool_call;
        setToolCalls((prev) => [
          ...prev,
          {
            id: tc.id,
            name: tc.name,
            args: JSON.stringify(tc.arguments, null, 2),
            status: 'running',
          },
        ]);
      } else if (chunk.type === 'tool_result' && chunk.tool_name) {
        setToolCalls((prev) =>
          prev.map((tc) =>
            tc.name === chunk.tool_name
              ? { ...tc, status: 'success', result: chunk.tool_result }
              : tc
          )
        );
      } else if (chunk.type === 'error' && chunk.error) {
        setToolCalls((prev) => prev.map((tc) => ({ ...tc, status: 'error', result: chunk.error })));
        addToast({ type: 'error', message: chunk.error });
      } else if (chunk.type === 'chat_done') {
        const finalContent = streamingContentRef.current;
        streamingContentRef.current = '';
        setIsStreaming(false);
        setStreamingContent('');
        if (finalContent || toolCalls.length > 0) {
          setMessages((prev) => [
            ...prev,
            {
              id: `msg-${Date.now()}`,
              role: 'assistant',
              content: finalContent || 'Task completed.',
            },
          ]);
        }
        setToolCalls([]);
        queryClient.invalidateQueries({ queryKey: ['sessions'] });
      }
    },
    [addToast, queryClient, navigate, setCurrentSessionKey]
  );

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;

    const userMessage = input.trim();
    setInput('');
    setShowSuggestions(false);

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: 'user', content: userMessage },
    ]);

    setIsStreaming(true);
    setStreamingContent('');
    streamingContentRef.current = '';
    setToolCalls([]);

    const abortStream = api.createChatStream(
      {
        session_key: activeSessionKey || undefined,
        message: userMessage,
        stream: true,
      },
      handleStreamChunk,
      (error) => {
        setIsStreaming(false);
        setStreamingContent('');
        addToast({ type: 'error', message: String(error) });
      }
    );

    (window as { abortChat?: () => void }).abortChat = abortStream;

  };

  const handleStop = () => {
    const abortFn = (window as { abortChat?: () => void }).abortChat;
    if (abortFn) abortFn();
    setIsStreaming(false);
    setStreamingContent('');
    setToolCalls([]);
    addToast({ type: 'info', message: 'Generation stopped' });
  };

  const handleNewChat = () => {
    setCurrentSessionKey(null);
    setMessages([]);
    setShowSuggestions(true);
    navigate('/chat');
    inputRef.current?.focus();
    setSessionsSidebarOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
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
      addToast({ type: 'error', message: 'Failed to copy' });
    }
  };

  const suggestions = [
    { text: '帮我审查一下当前仓库的代码结构。', label: '审查代码结构' },
    { text: '能告诉我有哪些自动化可以接入吗？', label: '查看自动化选项' },
    { text: '帮我写一个简单的 Python 脚本', label: '编写脚本' },
  ];

  const toolCallTagColor = (status: ToolCall['status']) => {
    if (status === 'running') return 'processing';
    if (status === 'success') return 'success';
    return 'error';
  };

  return (
    <div className="flex h-full bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      {/* Mobile Sessions Toggle Button */}
      <button
        onClick={() => setSessionsSidebarOpen(!sessionsSidebarOpen)}
        className="md:hidden fixed bottom-20 right-4 z-30 p-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-full shadow-lg shadow-primary-500/30 hover:shadow-xl hover:scale-105 transition-all"
      >
        {sessionsSidebarOpen ? <X className="w-5 h-5" /> : <MessageSquare className="w-5 h-5" />}
      </button>

      {/* Sessions Sidebar */}
      <div
        className={`
          ${sessionsSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          fixed md:relative z-20 h-screen
          w-80 bg-white/80 dark:bg-gray-800/80 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-700/50
          flex flex-col transition-transform duration-300 ease-out
        `}
      >
        <div className="p-4 border-b border-gray-200/50 dark:border-gray-700/50">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            size="large"
            onClick={handleNewChat}
          >
            New Chat
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto no-scrollbar p-3 space-y-2">
          {sessions?.map((session) => (
            <button
              key={session.key}
              onClick={() => handleSelectSession(session.key)}
              className={`w-full text-left px-4 py-3 rounded-xl transition-all ${
                activeSessionKey === session.key
                  ? 'bg-gradient-to-r from-primary-50 to-blue-50 dark:from-primary-900/30 dark:to-blue-900/20 text-primary-700 dark:text-primary-300'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
              }`}
            >
              <span className="text-sm font-medium truncate block">
                {session.title || session.key}
              </span>
              <span className="text-xs text-gray-500 mt-1 block">
                {session.message_count} messages
              </span>
            </button>
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

      {/* Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="h-16 px-6 flex items-center justify-between border-b border-gray-200/50 dark:border-gray-700/50 bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary-500/20">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Chat</h2>
              <p className="text-xs text-gray-500">Work with Nanobot</p>
            </div>
          </div>
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

        {/* Messages / Hero */}
        <div className="flex-1 min-h-0 overflow-y-auto no-scrollbar px-4 md:px-6 py-6 md:py-8">
          {messages.length === 0 && showSuggestions ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-600 dark:text-gray-300">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-100 to-blue-100 dark:from-primary-900/30 dark:to-blue-900/20 flex items-center justify-center mb-6 shadow-xl shadow-primary-500/10">
                <Bot className="w-10 h-10 text-primary-600" />
              </div>
              <h3 className="text-2xl font-bold mb-3 bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
                Hello, how can I help you today?
              </h3>
              <p className="text-sm text-gray-500 mb-8 max-w-md">
                Ask anything about your projects, code, or environment. I&apos;ll use your Nanobot
                setup to help.
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
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                      msg.role === 'user'
                        ? 'bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary-500/25'
                        : 'bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-600'
                    }`}
                  >
                    {msg.role === 'user' ? (
                      <User className="w-5 h-5 text-white" />
                    ) : (
                      <Bot className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                    )}
                  </div>
                  <div
                    className={`rounded-2xl px-5 py-4 max-w-[80%] ${
                      msg.role === 'user'
                        ? 'bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-lg shadow-primary-500/25'
                        : 'bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 shadow-sm'
                    }`}
                  >
                    <Tooltip title="Copy message" placement="top">
                      <Button
                        type="text"
                        size="small"
                        icon={
                          copiedMessageId === msg.id ? (
                            <CheckOutlined className="text-green-500" />
                          ) : (
                            <CopyOutlined
                              className={msg.role === 'user' ? 'text-white/70' : 'text-gray-400'}
                            />
                          )
                        }
                        className="float-right ml-2"
                        onClick={() => copyMessage(msg.content, msg.id)}
                      />
                    </Tooltip>
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ))}

              {/* Streaming content */}
              {isStreaming && (
                <>
                  {streamingContent && (
                    <div className="flex gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-600 flex items-center justify-center">
                        <Bot className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                      </div>
                      <div className="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl px-5 py-4 shadow-sm">
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                          <ReactMarkdown>{streamingContent}</ReactMarkdown>
                        </div>
                        <LoadingOutlined className="ml-2 text-primary-500" />
                      </div>
                    </div>
                  )}

                  {/* Tool calls */}
                  {toolCalls.length > 0 && (
                    <div className="ml-12 space-y-2">
                      {toolCalls.map((tc) => (
                        <div
                          key={tc.id}
                          className={`rounded-xl p-4 border ${
                            tc.status === 'running'
                              ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
                              : tc.status === 'success'
                              ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                              : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                          }`}
                        >
                          <div className="flex items-center gap-2 mb-2">
                            {tc.status === 'running' ? (
                              <LoadingOutlined className="text-blue-500" />
                            ) : tc.status === 'success' ? (
                              <CheckOutlined className="text-green-500" />
                            ) : (
                              <CloseOutlined className="text-red-500" />
                            )}
                            <span className="font-medium text-sm">{tc.name}</span>
                            <Tag color={toolCallTagColor(tc.status)}>{tc.status}</Tag>
                          </div>
                          {tc.args && (
                            <pre className="text-xs bg-gray-900 text-gray-100 p-2 rounded-lg overflow-x-auto">
                              {tc.args}
                            </pre>
                          )}
                          {tc.result && (
                            <pre className="text-xs mt-2 bg-gray-900 text-gray-100 p-2 rounded-lg overflow-x-auto max-h-32">
                              {tc.result.slice(0, 500)}
                              {tc.result.length > 500 && '...'}
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
    </div>
  );
}

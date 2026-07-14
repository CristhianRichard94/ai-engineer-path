"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { streamPrompt } from "../lib/api";
import type { ChatMessage } from "../lib/types";

interface ChatPanelProps {
  /** Null when no repo is ready yet — input stays disabled. */
  repoUrl: string | null;
  messages: ChatMessage[];
  onMessagesChange: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1.5" aria-hidden="true">
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 dark:bg-gray-300 animate-bounce [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 dark:bg-gray-300 animate-bounce [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 dark:bg-gray-300 animate-bounce [animation-delay:300ms]" />
    </span>
  );
}

function StreamingCursor() {
  return (
    <span
      aria-hidden="true"
      className="inline-block w-[2px] h-[1.1em] bg-white/70 ml-0.5 align-text-bottom animate-pulse"
    />
  );
}

function CodeBlock({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  async function handleCopy() {
    const text = preRef.current?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable or denied — silently no-op, button reverts on its own.
    }
  }

  return (
    <div className="group relative">
      <pre ref={preRef} {...props}>
        {children}
      </pre>
      <button
        type="button"
        onClick={handleCopy}
        aria-label="Copy code"
        className="absolute top-2 right-2 p-2 rounded-md bg-white/10 hover:bg-white/20 text-zinc-300 hover:text-white opacity-70 hover:opacity-100 focus-visible:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-opacity"
      >
        {copied ? (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-green-400"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
        <span role="status" className="sr-only">
          {copied ? "Copied" : ""}
        </span>
      </button>
    </div>
  );
}

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `msg-${Date.now()}-${idCounter}`;
}

export default function ChatPanel({ repoUrl, messages, onMessagesChange }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [announceComplete, setAnnounceComplete] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const autoScrollRef = useRef(true);

  const ready = repoUrl !== null;
  const canSend = ready && !streaming && input.trim().length > 0;

  const handleScroll = useCallback(() => {
    const el = messagesRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom <= 40;
    autoScrollRef.current = atBottom;
    setShowScrollButton(!atBottom);
  }, []);

  function scrollToBottomIfNeeded() {
    const el = messagesRef.current;
    if (!el || !autoScrollRef.current) return;
    el.scrollTop = el.scrollHeight;
  }

  function handleScrollToBottomClick() {
    const el = messagesRef.current;
    if (!el) return;
    autoScrollRef.current = true;
    el.scrollTop = el.scrollHeight;
    setShowScrollButton(false);
  }

  useEffect(() => {
    scrollToBottomIfNeeded();
  }, [messages]);

  function runStream(promptText: string, assistantId: string, history: { role: string; content: string }[]) {
    autoScrollRef.current = true;
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;

    let receivedAnyDelta = false;

    streamPrompt(
      repoUrl as string,
      promptText,
      {
        signal: controller.signal,
        onDelta: (delta) => {
          receivedAnyDelta = true;
          onMessagesChange((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + delta, pending: false, streaming: true }
                : m
            )
          );
          scrollToBottomIfNeeded();
        },
        onDone: () => {
          setStreaming(false);
          onMessagesChange((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, streaming: false, pending: false } : m
            )
          );
          setAnnounceComplete(true);
          inputRef.current?.focus();
        },
        onError: (message) => {
          setStreaming(false);
          onMessagesChange((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m;
              if (!receivedAnyDelta) {
                // Error before any tokens: replace with system-style error bubble.
                const isReindex = /not indexed|400/i.test(message);
                return {
                  ...m,
                  streaming: false,
                  pending: false,
                  content: "",
                  error: isReindex ? "reindex" : "retry",
                  errorMessage: "Something went wrong generating a response.",
                  sourcePrompt: promptText,
                };
              }
              // Mid-stream drop: keep partial text, show interrupted banner.
              return {
                ...m,
                streaming: false,
                pending: false,
                error: "retry",
                errorMessage: "Response interrupted — connection lost.",
                sourcePrompt: promptText,
              };
            })
          );
        },
      },
      history
    );
  }

  function buildHistory(): { role: string; content: string }[] {
    return messages
      .filter((m) => !m.streaming && !m.pending && !m.error)
      .map((m) => ({ role: m.role, content: m.content }));
  }

  function sendPrompt(promptText: string) {
    if (!repoUrl) return;
    const trimmed = promptText.trim();
    if (!trimmed) return;

    const history = buildHistory();

    const userMessage: ChatMessage = {
      id: nextId(),
      role: "user",
      content: trimmed,
    };
    const assistantId = nextId();
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      pending: true,
      streaming: true,
    };

    onMessagesChange((prev) => [...prev, userMessage, assistantPlaceholder]);
    setInput("");
    setAnnounceComplete(false);

    runStream(trimmed, assistantId, history);
  }

  function retryMessage(message: ChatMessage) {
    if (!message.sourcePrompt) return;
    const history = buildHistory();
    const assistantId = nextId();
    const freshPlaceholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      pending: true,
      streaming: true,
    };
    onMessagesChange((prev) => [
      ...prev.filter((m) => m.id !== message.id),
      freshPlaceholder,
    ]);
    setAnnounceComplete(false);
    runStream(message.sourcePrompt, assistantId, history);
  }

  function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSend) return;
    sendPrompt(input);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!canSend) return; // check state, not just visual disabled
      sendPrompt(input);
    }
  }

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const placeholder = ready ? "Ask about this repo…" : "Index a repo to start chatting…";

  return (
    <div className="flex flex-col h-full bg-gray-100 dark:bg-gray-800 rounded-lg p-4 sm:p-6">
      <div
        ref={messagesRef}
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto flex flex-col gap-3 mb-4"
      >
        {messages.length === 0 && (
          <div className="p-4 rounded-2xl self-start max-w-[85%] bg-zinc-200 dark:bg-gray-900 text-zinc-700 dark:text-zinc-300 text-sm">
            {ready
              ? "Repo indexed. Ask anything about its code or docs to get started."
              : "Index a repo to start chatting."}
          </div>
        )}
        {messages.map((message) => {
          if (message.role === "user") {
            return (
              <div
                key={message.id}
                className="animate-message-slide-in p-4 rounded-2xl rounded-br-md shadow-sm shadow-black/10 dark:shadow-black/30 bg-blue-800 self-end text-lg text-white"
              >
                {message.content}
              </div>
            );
          }

          if (message.error) {
            return (
              <div
                key={message.id}
                role="alert"
                className="message-fade-in p-4 rounded-2xl rounded-bl-md shadow-sm shadow-black/10 dark:shadow-black/30 self-start max-w-[85%] border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950 text-red-800 dark:text-red-200"
              >
                <p>{message.errorMessage}</p>
                {message.content && (
                  <p className="mt-2 text-white bg-gray-900 rounded p-2 text-base">
                    {message.content}
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => retryMessage(message)}
                  className="underline mt-2 inline-block focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
                >
                  {message.error === "reindex" ? "Re-index" : "Retry"}
                </button>
              </div>
            );
          }

          return (
            <div
              key={message.id}
              aria-busy={message.streaming ? "true" : undefined}
              className="animate-message-slide-in p-4 rounded-2xl rounded-bl-md shadow-sm shadow-black/10 dark:shadow-black/30 bg-gray-900 self-start text-lg text-white max-w-[85%]"
            >
              {message.pending ? (
                <ThinkingDots />
              ) : (
                <div className="content-crossfade">
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown
                      rehypePlugins={[rehypeHighlight]}
                      components={{
                        pre: CodeBlock,
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                  {message.streaming && <StreamingCursor />}
                </div>
              )}
            </div>
          );
        })}
        {showScrollButton && (
          <button
            type="button"
            onClick={handleScrollToBottomClick}
            aria-label="Scroll to latest message"
            className="absolute bottom-4 right-4 h-10 w-10 rounded-full bg-blue-800 hover:bg-blue-700 text-white shadow-md shadow-black/30 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        )}
      </div>

      {/* Separate sr-only status region for stream completion — intentionally
          NOT inside the same aria-live region as the streaming bubble. */}
      <div role="status" className="sr-only">
        {announceComplete ? "Response complete." : ""}
      </div>

      <form onSubmit={handleFormSubmit} className="flex w-full items-end">
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          rows={1}
          value={input}
          disabled={!ready || streaming}
          placeholder={placeholder}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 w-full p-2 border border-gray-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed dark:disabled:bg-gray-800 dark:disabled:text-gray-500 resize-none"
        />
        <button
          type="submit"
          disabled={!canSend}
          className="bg-blue-500 text-white px-4 py-2 rounded-r-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-blue-500/40 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </form>
    </div>
  );
}

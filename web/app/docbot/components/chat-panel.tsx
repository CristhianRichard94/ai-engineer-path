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
  /** Called when the backend responds 401 (session cookie expired/invalid). */
  onUnauthorized?: () => void;
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      <span className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-bounce [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-bounce [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-bounce [animation-delay:300ms]" />
    </span>
  );
}

function StreamingCursor() {
  return (
    <span
      aria-hidden="true"
      className="inline-block w-[2px] h-[1.1em] bg-gray-300 ml-0.5 align-text-bottom animate-pulse"
    />
  );
}

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `msg-${Date.now()}-${idCounter}`;
}

export default function ChatPanel({
  repoUrl,
  messages,
  onMessagesChange,
  onUnauthorized,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [announceComplete, setAnnounceComplete] = useState(false);
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
    autoScrollRef.current = distanceFromBottom <= 40;
  }, []);

  function scrollToBottomIfNeeded() {
    const el = messagesRef.current;
    if (!el || !autoScrollRef.current) return;
    el.scrollTop = el.scrollHeight;
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
        onUnauthorized: () => {
          onUnauthorized?.();
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
        className="flex-1 overflow-y-auto flex flex-col mb-4"
      >
        {messages.map((message) => {
          if (message.role === "user") {
            return (
              <div
                key={message.id}
                className="p-4 rounded-lg mb-4 bg-blue-800 self-end text-lg text-white"
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
                className="p-4 rounded-lg mb-4 self-start max-w-[85%] border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950 text-red-800 dark:text-red-200"
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
              className="p-4 rounded-lg mb-4 bg-gray-900 self-start text-lg text-white max-w-[85%]"
            >
              {message.pending ? (
                <ThinkingDots />
              ) : (
                <>
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                      {message.content}
                    </ReactMarkdown>
                  </div>
                  {message.streaming && <StreamingCursor />}
                </>
              )}
            </div>
          );
        })}
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

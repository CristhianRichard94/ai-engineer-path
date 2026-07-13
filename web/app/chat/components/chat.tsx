"use client";
import { useEffect, useRef, useState } from "react";
import { AIMessage } from "../types";
import { ApiError, LLMService, UnauthorizedError } from "../service";
const INITIAL_MESSAGE: AIMessage = {
  role: "assistant",
  content: "Welcome to the chat! Ask me anything.",
};
const service = new LLMService();

interface ChatComponentProps {
  /** Called when the backend responds 401 (session cookie expired/invalid). */
  onUnauthorized?: () => void;
}

function ChatComponent({ onUnauthorized }: ChatComponentProps) {
  const [lastMessage, setLastMessage] = useState("");
  const [inputText, setInputText] = useState("");
  const [loadingResponse, setLoadingResponse] = useState(false);
  const [conversation, setConversation] = useState<AIMessage[]>([
    INITIAL_MESSAGE,
  ]);
  const sendTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (lastMessage.trim() === "") return;

    if (sendTimeoutRef.current) return;
    sendTimeoutRef.current = setTimeout(() => {
      sendTimeoutRef.current = null;
    }, 1000); // 1 second throttle
    setLoadingResponse(true);
    service
      .sendMessage(conversation)
      .then((response) => {
        setConversation((prev) => [
          ...prev,
          { role: "assistant", content: response.content },
        ]);
        chatContainerRef.current?.scrollTo({
          top: chatContainerRef.current.scrollHeight,
          behavior: "smooth",
        });
      })
      .catch((err) => {
        if (err instanceof UnauthorizedError) {
          onUnauthorized?.();
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong sending your message. Please try again.";
        setConversation((prev) => [
          ...prev,
          { role: "assistant", content: message },
        ]);
        console.error("Error sending message:", err);
      })
      .finally(() => {
        setLoadingResponse(false);
      });
  }, [lastMessage]);

  const writeMessage = (message: string, submit?: boolean) => {
    if (message.trim() !== "" && submit) {
      sendMessage(message);
      setInputText("");
    } else {
      setInputText(message);
    }
  };
  const sendMessage = (lastMessage: string) => {
    setConversation((prev) => [
      ...prev,
      { role: "user", content: lastMessage },
    ]);
    setLastMessage(lastMessage);
  };
  return (
    <div className="w-full max-h-[70vh] bg-gray-100 dark:bg-gray-800 rounded-lg p-6 flex flex-col">
      <div
        className="previous-messages flex-1 min-h-0 overflow-y-auto mb-4 flex flex-col"
        ref={chatContainerRef}
      >
        {conversation.map((msg, index) => (
          <div
            key={index}
            className={`mb-4 p-4 rounded-lg ${
              msg.role === "user"
                ? "bg-blue-800 self-end"
                : "bg-gray-900 self-start"
            }`}
          >
            <div
              className="text-lg text-white mb-4 whitespace-pre-wrap break-words"
              dangerouslySetInnerHTML={{ __html: msg.content }}
            />
          </div>
        ))}
        {loadingResponse && (
          <div className="mb-4 p-4 rounded-lg bg-gray-900 self-start flex gap-1 items-center">
            <span className="h-2 w-2 rounded-full bg-white/70 animate-bounce [animation-delay:-0.3s]" />
            <span className="h-2 w-2 rounded-full bg-white/70 animate-bounce [animation-delay:-0.15s]" />
            <span className="h-2 w-2 rounded-full bg-white/70 animate-bounce" />
          </div>
        )}
      </div>

      <div className="input-container flex">
        <input
          type="text"
          value={inputText}
          onChange={(e) => writeMessage(e.target.value)}
          onKeyDown={(e) =>
            writeMessage(e.currentTarget.value, e.key === "Enter")
          }
          placeholder="Type your message..."
          disabled={loadingResponse}
          className="flex-1 w-full p-2 border border-gray-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={() => writeMessage(inputText, true)}
          className="bg-blue-500 text-white px-4 py-2 rounded-r-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={inputText.trim() === "" || loadingResponse}
        >
          Send
        </button>
      </div>
    </div>
  );
}

export default ChatComponent;

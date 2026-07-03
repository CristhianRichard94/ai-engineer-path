"use client";

import { useState } from "react";
import ChatComponent from "./components/chat";
import SessionExpiredBanner from "../components/session-expired-banner";

export default function ChatPage() {
  const [sessionExpired, setSessionExpired] = useState(false);

  return (
    <div className="flex flex-col flex-1">
      {sessionExpired && <SessionExpiredBanner returnTo="/chat" />}
      <div className="flex flex-col flex-1 items-center justify-center font-sans">
        <main className="flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-32 px-16 sm:items-start">
          <h1 className="text-4xl font-bold text-center mb-8">
            AI Chat Application
          </h1>
          <ChatComponent onUnauthorized={() => setSessionExpired(true)} />
        </main>
      </div>
    </div>
  );
}

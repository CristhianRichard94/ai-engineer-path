import { AIMessage } from "./types";

// Requests are proxied through this app's own origin (see next.config.ts
// `rewrites()`), so no cross-origin backend URL is ever exposed to the
// client and the session cookie set by /api/session is sent automatically.
const API_BASE_URL = "/api/chat";

export class UnauthorizedError extends Error {
  constructor() {
    super("Session expired.");
    this.name = "UnauthorizedError";
  }
}

export class LLMService {
  async sendMessage(conversation: AIMessage[]): Promise<AIMessage> {
    const response = await fetch(API_BASE_URL + "/message", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ conversation }),
    });

    if (response.status === 401) {
      throw new UnauthorizedError();
    }

    return response.json();
  }
}

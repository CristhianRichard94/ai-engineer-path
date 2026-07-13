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

// Mirrors app/docbot/lib/api.ts's ApiError so both surfaces handle
// non-2xx responses (rate limits, backend errors) the same way, instead of
// letting the caller silently push an empty/undefined message into the UI.
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export class LLMService {
  async sendMessage(conversation: AIMessage[]): Promise<AIMessage> {
    let response: Response;
    try {
      response = await fetch(API_BASE_URL + "/message", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ conversation }),
      });
    } catch {
      throw new ApiError(0, "Network error — could not reach the server.");
    }

    if (response.status === 401) {
      throw new UnauthorizedError();
    }

    let data: Record<string, unknown> = {};
    try {
      data = await response.json();
    } catch {
      // ignore parse failure, handled below by status check
    }

    if (!response.ok) {
      if (response.status === 429) {
        const retryAfter = response.headers.get("Retry-After");
        const waitMessage = retryAfter
          ? ` Try again in ${retryAfter}s.`
          : " Try again shortly.";
        const base = (data.error as string | undefined) || "Too many requests.";
        throw new ApiError(429, `${base}${waitMessage}`);
      }

      const message =
        (data.error as string | undefined) ||
        `Request failed with status ${response.status}.`;
      throw new ApiError(response.status, message);
    }

    return data as unknown as AIMessage;
  }
}

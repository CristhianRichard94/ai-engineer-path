// Backend API client for the doc-bot indexing/prompt service.
// Requests are proxied through this app's own origin (see next.config.ts
// `rewrites()`), so no cross-origin backend URL is ever exposed to the
// client and the session cookie set by /api/session is sent automatically.

import type {
  IndexJobStatusResponse,
  IndexPostResponse,
  StreamEvent,
} from "./types";

const API_BASE = "/api/docbot";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/**
 * POST /api/docbot/index
 * Returns either a dispatched job (202) or an already-indexed result (200).
 * Throws ApiError on 400/401/5xx or network failure.
 */
export async function postIndex(url: string): Promise<IndexPostResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
  } catch {
    throw new ApiError(0, "Network error — could not reach the server.");
  }

  let data: Record<string, unknown> = {};
  try {
    data = await response.json();
  } catch {
    // ignore parse failure, handled below by status check
  }

  if (response.status === 202) {
    return {
      kind: "dispatched",
      job_id: data.job_id as string,
      commit: data.commit as string,
    };
  }

  if (response.status === 200 && data.status === "already_indexed") {
    return { kind: "already_indexed", commit: data.commit as string };
  }

  const message =
    (data.error as string | undefined) ||
    `Request failed with status ${response.status}.`;
  throw new ApiError(response.status, message);
}

/**
 * GET /api/docbot/index/{job_id}
 */
export async function getIndexStatus(
  jobId: string
): Promise<IndexJobStatusResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/index/${encodeURIComponent(jobId)}`);
  } catch {
    throw new ApiError(0, "Network error while polling job status.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, `Polling failed with status ${response.status}.`);
  }

  return (await response.json()) as IndexJobStatusResponse;
}

export interface HistoryEntry {
  role: string;
  content: string;
}

export interface StreamPromptHandlers {
  onDelta: (delta: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
  /** Called (in addition to onError) when the backend responds 401. */
  onUnauthorized?: () => void;
  signal?: AbortSignal;
}

/**
 * POST /api/docbot/prompt/stream
 * Manually parses a text/event-stream response body via fetch + ReadableStream,
 * since EventSource does not support POST bodies.
 *
 * Handles the documented contract:
 * - Non-SSE synchronous 400/401 JSON error (validation failure / repo not
 *   indexed / expired session).
 * - SSE stream of `data: {"delta": "..."}` events, terminated by
 *   `data: {"done": true}` or `data: {"error": "..."}`.
 */
export async function streamPrompt(
  url: string,
  prompt: string,
  handlers: StreamPromptHandlers,
  history?: HistoryEntry[]
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/prompt/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, prompt, history: history ?? [] }),
      signal: handlers.signal,
    });
  } catch {
    handlers.onError("Network error — could not reach the server.");
    return;
  }

  const contentType = response.headers.get("content-type") || "";

  if (!response.ok || !contentType.includes("text/event-stream")) {
    if (response.status === 401) {
      handlers.onUnauthorized?.();
      handlers.onError("Your session expired.");
      return;
    }

    // Synchronous JSON error response (e.g. 400 validation failure).
    let message = `Request failed with status ${response.status}.`;
    try {
      const data = await response.json();
      if (data && typeof data.error === "string") {
        message = data.error;
      }
    } catch {
      // ignore
    }
    handlers.onError(message);
    return;
  }

  if (!response.body) {
    handlers.onError("No response body received from server.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line ("\n\n").
      let separatorIndex: number;
      while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);

        const event = parseSseEvent(rawEvent);
        if (!event) continue;

        if ("delta" in event) {
          handlers.onDelta(event.delta);
        } else if ("done" in event) {
          handlers.onDone();
          return;
        } else if ("error" in event) {
          handlers.onError(event.error);
          return;
        }
      }
    }

    // Stream ended without an explicit terminal event — treat as a dropped
    // connection.
    handlers.onError("Response interrupted — connection lost.");
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return;
    }
    handlers.onError("Response interrupted — connection lost.");
  }
}

function parseSseEvent(rawEvent: string): StreamEvent | null {
  const dataLines = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());

  if (dataLines.length === 0) return null;

  const payload = dataLines.join("\n");
  try {
    return JSON.parse(payload) as StreamEvent;
  } catch {
    return null;
  }
}

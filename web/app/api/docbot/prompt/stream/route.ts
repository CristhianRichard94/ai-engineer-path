import { NextRequest } from "next/server";
import { getClientIp } from "../../../../../lib/rate-limit";
import { envInt, proxyPost, rateLimitOrNull } from "../../../../../lib/proxy";

// Streaming (SSE) prompt endpoint — this is what the frontend actually
// calls (see app/docbot/lib/api.ts `streamPrompt`). Shares the same
// rate-limit bucket key prefix as /api/docbot/prompt so the two endpoints
// draw from one shared "questions asked" budget per IP rather than each
// getting their own.
//
// proxyPost() streams the upstream Response.body straight through, so the
// text/event-stream response is forwarded to the client incrementally
// rather than buffered.

const DOCBOT_BACKEND_URL = process.env.DOCBOT_BACKEND_URL || "http://127.0.0.1:5000";
const DOCBOT_PROMPT_RATE_LIMIT_MAX = envInt("DOCBOT_PROMPT_RATE_LIMIT_MAX", 20);
const DOCBOT_PROMPT_RATE_LIMIT_WINDOW_MS = envInt(
  "DOCBOT_PROMPT_RATE_LIMIT_WINDOW_MS",
  10 * 60 * 1000
);

export async function POST(request: NextRequest) {
  const ip = getClientIp(request);
  const limited = rateLimitOrNull(
    `docbot-prompt:${ip}`,
    DOCBOT_PROMPT_RATE_LIMIT_MAX,
    DOCBOT_PROMPT_RATE_LIMIT_WINDOW_MS
  );
  if (limited) return limited;

  return proxyPost(`${DOCBOT_BACKEND_URL}/api/prompt/stream`, request);
}

import { NextRequest } from "next/server";
import { getClientIp } from "../../../../lib/rate-limit";
import { envInt, proxyPost, rateLimitOrNull } from "../../../../lib/proxy";

// Non-streaming prompt endpoint. Shares the same rate-limit bucket key
// prefix as /api/docbot/prompt/stream (see that route) so a caller can't
// double their effective budget by mixing the two — both count as "asking
// the doc bot a question" against one shared cap per IP.

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

  return proxyPost(`${DOCBOT_BACKEND_URL}/api/prompt`, request);
}

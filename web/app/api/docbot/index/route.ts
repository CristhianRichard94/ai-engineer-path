import { NextRequest } from "next/server";
import { getClientIp } from "../../../../lib/rate-limit";
import { envInt, proxyPost, rateLimitOrNull } from "../../../../lib/proxy";

// Explicit route handler so indexing requests are rate-limited before they
// reach the Flask backend. GET /api/docbot/index/{job_id} (status polling)
// isn't covered by this file and keeps going through the next.config.ts
// rewrite unchanged — polling an existing job is cheap and not what this
// cap is meant to protect against.
//
// Indexing is the most expensive operation in this app (clones/embeds a
// whole repo), so it gets a much stricter cap than prompts: a handful per
// hour per IP.

const DOCBOT_BACKEND_URL = process.env.DOCBOT_BACKEND_URL || "http://127.0.0.1:5000";
const DOCBOT_INDEX_RATE_LIMIT_MAX = envInt("DOCBOT_INDEX_RATE_LIMIT_MAX", 5);
const DOCBOT_INDEX_RATE_LIMIT_WINDOW_MS = envInt(
  "DOCBOT_INDEX_RATE_LIMIT_WINDOW_MS",
  60 * 60 * 1000
);

export async function POST(request: NextRequest) {
  const ip = getClientIp(request);
  const limited = rateLimitOrNull(
    `docbot-index:${ip}`,
    DOCBOT_INDEX_RATE_LIMIT_MAX,
    DOCBOT_INDEX_RATE_LIMIT_WINDOW_MS
  );
  if (limited) return limited;

  return proxyPost(`${DOCBOT_BACKEND_URL}/api/index`, request);
}

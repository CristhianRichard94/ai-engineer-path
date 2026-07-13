import { NextRequest } from "next/server";
import { getClientIp } from "../../../../lib/rate-limit";
import { envInt, proxyPost, rateLimitOrNull } from "../../../../lib/proxy";

// Explicit route handler (rather than relying on the next.config.ts
// rewrite) so we can rate-limit before the request ever reaches the FastAPI
// backend. Filesystem routes take precedence over config-level rewrites for
// the same path, so this fully replaces the rewrite for /api/chat/message.
//
// No per-user identity is available here (single shared passcode, session
// cookie carries no user id and is re-signed on every request), so limiting
// is per-IP, same as the login endpoint.

const CHAT_BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://127.0.0.1:8000";
const CHAT_RATE_LIMIT_MAX = envInt("CHAT_RATE_LIMIT_MAX", 15);
const CHAT_RATE_LIMIT_WINDOW_MS = envInt("CHAT_RATE_LIMIT_WINDOW_MS", 10 * 60 * 1000);

export async function POST(request: NextRequest) {
  const ip = getClientIp(request);
  const limited = rateLimitOrNull(`chat:${ip}`, CHAT_RATE_LIMIT_MAX, CHAT_RATE_LIMIT_WINDOW_MS);
  if (limited) return limited;

  return proxyPost(`${CHAT_BACKEND_URL}/api/message`, request);
}

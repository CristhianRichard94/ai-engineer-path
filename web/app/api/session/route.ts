import { NextRequest, NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_SECONDS,
  createSessionValue,
  passcodeMatches,
} from "../../../lib/session";
import {
  checkLoginLockout,
  ensureSweepScheduled,
  getClientIp,
  isSharedClientKey,
  recordLoginFailure,
  recordLoginSuccess,
} from "../../../lib/rate-limit";

// Runs in the Node.js runtime (default for route handlers) so it shares the
// same in-memory rate-limit state as any other Node-runtime code in this
// process. See lib/rate-limit.ts for the single-instance caveat and the
// escalating-lockout parameters (free attempts, backoff growth, cap, and the
// separate low cap applied when the resolved client key is shared/ambiguous
// rather than scoped to one visitor).

export async function POST(request: NextRequest) {
  ensureSweepScheduled();

  const ip = getClientIp(request);
  const loginKey = `login:${ip}`;
  // Without TRUST_PROXY_HEADERS, `ip` is a sentinel shared by every visitor
  // — the lockout must not be allowed to escalate to the full 24h cap in
  // that case, or one anonymous, unauthenticated caller could lock every
  // visitor (owner included) out of login for a day, repeatably. See
  // lib/rate-limit.ts's recordLoginFailure for the cap this feeds into.
  const sharedKey = isSharedClientKey(ip);

  const lockout = checkLoginLockout(loginKey);
  if (!lockout.allowed) {
    return NextResponse.json(
      { error: "Too many attempts. Try again later." },
      { status: 429, headers: { "Retry-After": String(lockout.retryAfterSeconds) } }
    );
  }

  const sitePasscode = process.env.SITE_PASSCODE;
  const sessionSecret = process.env.SESSION_SECRET;
  if (!sitePasscode || !sessionSecret) {
    console.error(
      "SITE_PASSCODE and/or SESSION_SECRET env vars are not set — refusing all logins."
    );
    return NextResponse.json(
      { error: "Server is misconfigured. Please contact the site owner." },
      { status: 500 }
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const passcode =
    body && typeof body === "object" && "passcode" in body
      ? (body as { passcode: unknown }).passcode
      : undefined;

  if (typeof passcode !== "string" || passcode.trim() === "") {
    return NextResponse.json({ error: "Passcode is required." }, { status: 400 });
  }

  const isValid = await passcodeMatches(passcode.trim(), sitePasscode);
  if (!isValid) {
    recordLoginFailure(loginKey, sharedKey);
    return NextResponse.json({ error: "Incorrect passcode." }, { status: 401 });
  }

  recordLoginSuccess(loginKey);
  const sessionValue = await createSessionValue(sessionSecret);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, sessionValue, {
    httpOnly: true,
    // Skip `Secure` outside production so local `http://localhost` dev works
    // without HTTPS. Always enforced in production.
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return response;
}

import { NextRequest, NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_SECONDS,
  createSessionValue,
  passcodeMatches,
} from "../../../lib/session";
import { checkRateLimit, ensureSweepScheduled } from "../../../lib/rate-limit";

// Runs in the Node.js runtime (default for route handlers) so it shares the
// same in-memory rate-limit bucket as any other Node-runtime code in this
// process. See lib/rate-limit.ts for the single-instance caveat.

const RATE_LIMIT_MAX_ATTEMPTS = 5;
const RATE_LIMIT_WINDOW_MS = 60 * 1000;

function getClientIp(request: NextRequest): string {
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) return forwardedFor.split(",")[0].trim();
  const realIp = request.headers.get("x-real-ip");
  if (realIp) return realIp;
  return "unknown";
}

export async function POST(request: NextRequest) {
  ensureSweepScheduled(RATE_LIMIT_WINDOW_MS);

  const ip = getClientIp(request);
  const rateLimit = checkRateLimit(ip, RATE_LIMIT_MAX_ATTEMPTS, RATE_LIMIT_WINDOW_MS);
  if (!rateLimit.allowed) {
    return NextResponse.json(
      { error: "Too many attempts. Try again in a moment." },
      { status: 429, headers: { "Retry-After": String(rateLimit.retryAfterSeconds) } }
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
    return NextResponse.json({ error: "Incorrect passcode." }, { status: 401 });
  }

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

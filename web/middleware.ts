import { NextRequest, NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_SECONDS,
  createSessionValue,
  verifySessionValue,
} from "./lib/session";

// Protects the hub and both app routes behind the shared-passcode session
// cookie. `/login` and `/api/session` are intentionally left unprotected
// (the matcher below excludes them, along with static assets).
export async function middleware(request: NextRequest) {
  const sessionSecret = process.env.SESSION_SECRET;
  const cookieValue = request.cookies.get(SESSION_COOKIE_NAME)?.value;

  const isValid = sessionSecret
    ? await verifySessionValue(cookieValue, sessionSecret)
    : false;

  if (!isValid) {
    // Proxied backend calls (fetch from client code) need a real 401 status
    // so the page can detect it and show the dismissible session-expired
    // banner, instead of transparently following a redirect to an HTML page.
    if (request.nextUrl.pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Session expired." }, { status: 401 });
    }

    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("returnTo", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Sliding expiry: renew the cookie on every authenticated request so an
  // active user never gets logged out mid-session.
  const response = NextResponse.next();
  if (sessionSecret) {
    const renewedValue = await createSessionValue(sessionSecret);
    response.cookies.set(SESSION_COOKIE_NAME, renewedValue, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: SESSION_MAX_AGE_SECONDS,
    });
  }
  return response;
}

export const config = {
  matcher: [
    /*
     * Protect everything except:
     * - /login (passcode entry)
     * - /api/session (passcode check endpoint)
     * - Next.js internals and static assets
     */
    "/((?!login|api/session|_next/static|_next/image|favicon.ico).*)",
  ],
};

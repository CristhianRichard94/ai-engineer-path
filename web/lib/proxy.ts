// Shared helpers for route handlers that rate-limit a request and then
// proxy it through to one of the external backends (FastAPI chat service,
// Flask docbot service). Centralized here so each route file only has to
// declare its limit/window and the upstream URL.

import { NextRequest, NextResponse } from "next/server";
import { checkRateLimit, ensureSweepScheduled, RateLimitResult } from "./rate-limit";

/**
 * Runs a fixed-window rate-limit check for `key` and returns a ready-to-send
 * 429 response if the caller is over the limit, or `null` if the request may
 * proceed.
 */
export function rateLimitOrNull(
  key: string,
  limit: number,
  windowMs: number
): NextResponse | null {
  ensureSweepScheduled();
  const result: RateLimitResult = checkRateLimit(key, limit, windowMs);
  if (result.allowed) return null;

  return NextResponse.json(
    { error: "Too many requests. Please slow down." },
    { status: 429, headers: { "Retry-After": String(result.retryAfterSeconds) } }
  );
}

/**
 * Reads a positive integer from an env var, falling back to `defaultValue`
 * if unset or invalid. Used so rate-limit caps are configurable without
 * code changes.
 */
export function envInt(name: string, defaultValue: number): number {
  const raw = process.env[name];
  if (!raw) return defaultValue;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : defaultValue;
}

/**
 * Forwards a POST request's raw body to `upstreamUrl` and streams the
 * upstream response straight back to the client, preserving status and the
 * content-type/cache-control headers. Works uniformly for plain JSON
 * responses and Server-Sent Events streams (e.g. the docbot prompt/stream
 * endpoint) since `Response.body` is passed through as-is either way.
 */
export async function proxyPost(
  upstreamUrl: string,
  request: NextRequest
): Promise<NextResponse> {
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: "POST",
      headers: { "Content-Type": request.headers.get("content-type") || "application/json" },
      body,
    });
  } catch {
    return NextResponse.json(
      { error: "Could not reach the backend service." },
      { status: 502 }
    );
  }

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  const cacheControl = upstream.headers.get("cache-control");
  if (cacheControl) responseHeaders.set("cache-control", cacheControl);

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

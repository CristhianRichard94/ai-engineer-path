// In-memory, per-key rate limiting primitives shared by every route handler
// in this app (login, chat, docbot). Two limiter shapes are exposed:
//
//   - `checkRateLimit` — a plain fixed-window counter ("N attempts per
//     window"). Used for the chat/docbot endpoints, where a flat cap is
//     enough since they sit behind the session cookie already.
//   - `checkLoginLockout` / `recordLoginFailure` / `recordLoginSuccess` — an
//     escalating-lockout limiter purpose-built for the passcode login, where
//     a flat window is too easy to brute-force (wait out 60s, try 5 more).
//     Consecutive failures grow the lockout exponentially; a success resets
//     the counter for that key.
//
// Callers namespace their keys (e.g. `login:${ip}`, `chat:${ip}`) so a
// single IP hitting multiple endpoints doesn't share one bucket across them.
//
// NOTE: this state lives in the Node.js process memory. It is single-instance
// only — if this app is ever deployed across multiple instances/replicas
// behind a load balancer, each instance will track its own counters and the
// effective limit becomes (limit * instanceCount). That's an acceptable
// tradeoff at this portfolio scale (single small deployment); a real
// multi-instance deployment would need a shared store (e.g. Redis) instead.

export interface RateLimitResult {
  allowed: boolean;
  retryAfterSeconds: number;
}

// ---------------------------------------------------------------------------
// Bounded-size map helper (defense in depth)
// ---------------------------------------------------------------------------
//
// Even with the `getClientIp` hardening below, a caller who *can* vary their
// effective rate-limit key (e.g. once TRUST_PROXY_HEADERS is enabled for a
// real deployment, or any future key source) could otherwise flood these
// Maps with distinct keys forever, growing them without bound — a memory
// exhaustion DoS independent of whether any individual key's limit is ever
// exceeded. Cap each map's size and evict the oldest entry (by insertion
// order, which Map preserves) once the cap is hit, regardless of which IP
// source is in play.

const MAX_TRACKED_KEYS = 5000;

// True LRU-on-write: `Map` preserves insertion order, but `Map.set` on an
// already-present key does NOT move it to the end — it only updates the
// value in place. Without the delete-then-reinsert below, eviction would
// track "longest since first ever seen" rather than "least recently
// updated," which (once TRUST_PROXY_HEADERS=1 makes keys attacker-varied)
// lets an attacker flood the map with fresh keys to evict a target's entry
// out from under it mid-lockout — silently resetting someone else's state.
function setBounded<V>(map: Map<string, V>, key: string, value: V): void {
  if (map.has(key)) {
    map.delete(key);
  } else if (map.size >= MAX_TRACKED_KEYS) {
    const oldestKey = map.keys().next().value;
    if (oldestKey !== undefined) map.delete(oldestKey);
  }
  map.set(key, value);
}

// ---------------------------------------------------------------------------
// Fixed-window limiter (chat/docbot endpoints)
// ---------------------------------------------------------------------------

interface Bucket {
  count: number;
  windowStartMs: number;
}

const buckets = new Map<string, Bucket>();

/**
 * Returns whether `key` is within `limit` attempts per `windowMs`
 * milliseconds. Every call (allowed or not) counts as an attempt once the
 * window has started, so retries against a rejected request don't extend
 * the caller's budget.
 */
export function checkRateLimit(
  key: string,
  limit: number,
  windowMs: number
): RateLimitResult {
  const now = Date.now();
  const existing = buckets.get(key);

  if (!existing || now - existing.windowStartMs >= windowMs) {
    setBounded(buckets, key, { count: 1, windowStartMs: now });
    return { allowed: true, retryAfterSeconds: 0 };
  }

  if (existing.count < limit) {
    existing.count += 1;
    setBounded(buckets, key, existing);
    return { allowed: true, retryAfterSeconds: 0 };
  }

  const retryAfterSeconds = Math.ceil(
    (existing.windowStartMs + windowMs - now) / 1000
  );
  return { allowed: false, retryAfterSeconds: Math.max(retryAfterSeconds, 1) };
}

// ---------------------------------------------------------------------------
// Escalating lockout (login endpoint)
// ---------------------------------------------------------------------------

interface LoginState {
  consecutiveFailures: number;
  lockedUntilMs: number;
  lastAttemptMs: number;
}

const loginStates = new Map<string, LoginState>();

// The first LOGIN_FREE_ATTEMPTS failures don't trigger a lockout at all
// (keeps the UX painless for someone who just mistyped the passcode once or
// twice). From the next failure on, the lockout duration doubles each time:
// 30s, 60s, 120s, 240s, ... up to a 24h cap. That makes online brute-forcing
// a short passcode impractical without needing a shared store.
const LOGIN_FREE_ATTEMPTS = 5;
const LOGIN_BASE_LOCKOUT_MS = 30 * 1000;
const LOGIN_MAX_LOCKOUT_MS = 24 * 60 * 60 * 1000;
// If a key hasn't been touched in this long, forget its failure history
// entirely (both to let a genuine user try again eventually, and so the
// map doesn't retain state forever).
const LOGIN_FAILURE_RESET_MS = 24 * 60 * 60 * 1000;

// When the resolved "client identity" isn't actually per-client (see
// getClientIp below — by default, without TRUST_PROXY_HEADERS, every caller
// resolves to the same sentinel), the login-lockout key ends up shared by
// every visitor, owner included. Letting THAT key escalate all the way to a
// 24h lockout turns the anti-brute-force feature into a trivial anonymous
// DoS: ~18 scripted failed POSTs from anyone, no credentials required, locks
// every visitor out of login for a day, repeatably.
//
// So the full exponential-to-24h escalation is reserved for keys we believe
// are actually scoped to one client (TRUST_PROXY_HEADERS=1 with a real IP).
// Any key that resolves to the shared/ambiguous sentinel is capped at a much
// lower ceiling — long enough to still meaningfully slow down brute-forcing
// a short passcode, short enough that a legitimate visitor is never locked
// out for more than a couple of minutes because of someone else's attempts.
const LOGIN_SHARED_KEY_MAX_LOCKOUT_MS = 90 * 1000;

/** Checks whether `key` is currently locked out, without recording an attempt. */
export function checkLoginLockout(key: string): RateLimitResult {
  const now = Date.now();
  const state = loginStates.get(key);
  if (!state) return { allowed: true, retryAfterSeconds: 0 };

  if (now - state.lastAttemptMs >= LOGIN_FAILURE_RESET_MS) {
    loginStates.delete(key);
    return { allowed: true, retryAfterSeconds: 0 };
  }

  if (now < state.lockedUntilMs) {
    const retryAfterSeconds = Math.ceil((state.lockedUntilMs - now) / 1000);
    return { allowed: false, retryAfterSeconds: Math.max(retryAfterSeconds, 1) };
  }

  return { allowed: true, retryAfterSeconds: 0 };
}

/**
 * Records a failed login attempt for `key`, extending the lockout if
 * warranted. `isSharedKey` must be true whenever `key` isn't reliably scoped
 * to a single client (i.e. derived from `getClientIp` without
 * TRUST_PROXY_HEADERS) — it caps how far the lockout is allowed to escalate,
 * see LOGIN_SHARED_KEY_MAX_LOCKOUT_MS above.
 */
export function recordLoginFailure(key: string, isSharedKey: boolean): void {
  const now = Date.now();
  const existing = loginStates.get(key);
  const stillFresh = existing && now - existing.lastAttemptMs < LOGIN_FAILURE_RESET_MS;
  const consecutiveFailures = (stillFresh ? existing!.consecutiveFailures : 0) + 1;

  let lockedUntilMs = 0;
  if (consecutiveFailures > LOGIN_FREE_ATTEMPTS) {
    const exponent = consecutiveFailures - LOGIN_FREE_ATTEMPTS - 1;
    const cap = isSharedKey ? LOGIN_SHARED_KEY_MAX_LOCKOUT_MS : LOGIN_MAX_LOCKOUT_MS;
    const lockoutMs = Math.min(LOGIN_BASE_LOCKOUT_MS * 2 ** exponent, cap);
    lockedUntilMs = now + lockoutMs;
  }

  setBounded(loginStates, key, { consecutiveFailures, lockedUntilMs, lastAttemptMs: now });
}

/** Records a successful login for `key`, clearing any failure history. */
export function recordLoginSuccess(key: string): void {
  loginStates.delete(key);
}

// ---------------------------------------------------------------------------
// Housekeeping
// ---------------------------------------------------------------------------

// Periodically sweep stale entries so these Maps don't grow unbounded over a
// long-running process. Not critical at this scale, but cheap insurance.
// Uses a generous fixed staleness threshold rather than each caller's own
// window, since a single shared sweep timer can't know every endpoint's
// window size — this just needs to be larger than any window in use.
const SWEEP_INTERVAL_MS = 10 * 60 * 1000;
const BUCKET_STALE_AFTER_MS = 24 * 60 * 60 * 1000;
let sweepTimer: ReturnType<typeof setInterval> | null = null;

export function ensureSweepScheduled() {
  if (sweepTimer) return;
  sweepTimer = setInterval(() => {
    const now = Date.now();
    for (const [key, bucket] of buckets) {
      if (now - bucket.windowStartMs >= BUCKET_STALE_AFTER_MS) buckets.delete(key);
    }
    for (const [key, state] of loginStates) {
      if (now - state.lastAttemptMs >= LOGIN_FAILURE_RESET_MS) loginStates.delete(key);
    }
  }, SWEEP_INTERVAL_MS);
  // Don't keep the process alive just for this timer.
  if (typeof sweepTimer === "object" && "unref" in sweepTimer) {
    (sweepTimer as unknown as { unref: () => void }).unref();
  }
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

// `X-Forwarded-For` / `X-Real-IP` are set by *client* request headers unless
// something in front of this app actively strips and rewrites them. Next.js
// route handlers (this Next.js version, self-hosted) don't expose the raw
// TCP connection's remote address — `NextRequest` has no `.ip`/geo field
// (that only ever existed on Vercel's managed runtime) — so there is no
// framework-level non-spoofable IP to fall back to here.
//
// Trusting these headers unconditionally would let any client set
// `X-Forwarded-For: <anything>` on every request and get a fresh rate-limit
// bucket each time, fully bypassing both the login lockout and the
// chat/docbot caps. This repo has no confirmed, enforced reverse-proxy
// topology that guarantees a single hop strips/overwrites client-supplied
// values before they reach this app, so the secure default is to NOT trust
// them.
//
// If this app is deployed behind a reverse proxy you control (and have
// verified strips any client-supplied X-Forwarded-For/X-Real-IP before
// setting its own), set `TRUST_PROXY_HEADERS=1` to opt in. Until that's
// explicitly configured, every caller collapses onto one shared bucket key
// — which is a global rate limit rather than a per-client one, but it can't
// be spoofed around, and it's paired with the map-size cap below as
// defense in depth regardless.
const TRUST_PROXY_HEADERS =
  process.env.TRUST_PROXY_HEADERS === "1" || process.env.TRUST_PROXY_HEADERS === "true";

// Sentinel values getClientIp returns when it can't (or won't) resolve a
// value that's actually scoped to one client. Exported so callers — notably
// the login lockout — can tell a "real" per-client key apart from one that
// may be shared by every visitor, and adjust their own escalation logic
// accordingly (see LOGIN_SHARED_KEY_MAX_LOCKOUT_MS above).
export const UNVERIFIED_CLIENT_KEY = "unverified-client";
export const UNKNOWN_CLIENT_KEY = "unknown";

/** True if `ip` (as returned by getClientIp) is a shared/ambiguous sentinel rather than a real per-client value. */
export function isSharedClientKey(ip: string): boolean {
  return ip === UNVERIFIED_CLIENT_KEY || ip === UNKNOWN_CLIENT_KEY;
}

if (TRUST_PROXY_HEADERS) {
  // Fires once per process (module-load time), which is effectively a
  // startup warning for every route that imports this module. Intentionally
  // loud: flipping this on without verifying the precondition silently
  // reopens the header-spoofing hole this module otherwise defends against.
  console.warn(
    "[rate-limit] TRUST_PROXY_HEADERS is enabled — X-Forwarded-For / " +
      "X-Real-IP will now be trusted as client identity for rate limiting. " +
      "This is ONLY safe if your reverse proxy fully REPLACES these headers " +
      "(strips any client-supplied value) before forwarding the request — " +
      "if a client can still inject its own X-Forwarded-For and have it " +
      "survive to this app, rate limits are trivially bypassable. This code " +
      "also takes the LEFTMOST X-Forwarded-For entry, which is only correct " +
      "if your proxy sets/replaces that header itself (single trusted hop); " +
      "if your topology instead APPENDS to an existing header (multiple " +
      "hops, some of which may be attacker-controlled), the leftmost entry " +
      "is not the value you want and this logic needs to change to pick the " +
      "correct hop for your setup."
  );
}

export function getClientIp(request: Request): string {
  if (!TRUST_PROXY_HEADERS) return UNVERIFIED_CLIENT_KEY;

  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) return forwardedFor.split(",")[0].trim();
  const realIp = request.headers.get("x-real-ip");
  if (realIp) return realIp;
  return UNKNOWN_CLIENT_KEY;
}

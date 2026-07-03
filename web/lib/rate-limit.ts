// Simple in-memory, per-IP, fixed-window rate limiter.
//
// NOTE: this state lives in the Node.js process memory. It is single-instance
// only — if this app is ever deployed across multiple instances/replicas
// behind a load balancer, each instance will track its own counters and the
// effective limit becomes (limit * instanceCount). That's an acceptable
// tradeoff at this portfolio scale (single small deployment); a real
// multi-instance deployment would need a shared store (e.g. Redis) instead.

interface Bucket {
  count: number;
  windowStartMs: number;
}

const buckets = new Map<string, Bucket>();

export interface RateLimitResult {
  allowed: boolean;
  retryAfterSeconds: number;
}

/**
 * Returns whether `key` (typically an IP address) is within `limit` attempts
 * per `windowMs` milliseconds.
 */
export function checkRateLimit(
  key: string,
  limit: number,
  windowMs: number
): RateLimitResult {
  const now = Date.now();
  const existing = buckets.get(key);

  if (!existing || now - existing.windowStartMs >= windowMs) {
    buckets.set(key, { count: 1, windowStartMs: now });
    return { allowed: true, retryAfterSeconds: 0 };
  }

  if (existing.count < limit) {
    existing.count += 1;
    return { allowed: true, retryAfterSeconds: 0 };
  }

  const retryAfterSeconds = Math.ceil(
    (existing.windowStartMs + windowMs - now) / 1000
  );
  return { allowed: false, retryAfterSeconds: Math.max(retryAfterSeconds, 1) };
}

// Periodically sweep stale buckets so this Map doesn't grow unbounded over
// a long-running process. Not critical at this scale, but cheap insurance.
const SWEEP_INTERVAL_MS = 10 * 60 * 1000;
let sweepTimer: ReturnType<typeof setInterval> | null = null;

export function ensureSweepScheduled(windowMs: number) {
  if (sweepTimer) return;
  sweepTimer = setInterval(() => {
    const now = Date.now();
    for (const [key, bucket] of buckets) {
      if (now - bucket.windowStartMs >= windowMs) buckets.delete(key);
    }
  }, SWEEP_INTERVAL_MS);
  // Don't keep the process alive just for this timer.
  if (typeof sweepTimer === "object" && "unref" in sweepTimer) {
    (sweepTimer as unknown as { unref: () => void }).unref();
  }
}

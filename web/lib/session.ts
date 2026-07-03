// Signed session cookie helpers.
//
// The cookie value is `${base64url(payloadJson)}.${base64url(hmacSignature)}`.
// The payload only carries an expiry timestamp — there's no per-user identity
// in this app (single shared passcode), so there is nothing else to store.
// Signing with SESSION_SECRET means the cookie can't be forged or its expiry
// extended by a client that doesn't know the secret.
//
// Uses Web Crypto (`crypto.subtle`), which is available both in the Node.js
// runtime (route handlers) and the Edge runtime (middleware), so the same
// code works in both places.

export const SESSION_COOKIE_NAME = "site_session";
export const SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60; // 7 days

interface SessionPayload {
  exp: number; // unix seconds
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  const base64 = btoa(binary);
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const withPadding = padded + "=".repeat((4 - (padded.length % 4)) % 4);
  const binary = atob(withPadding);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function importHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

async function sign(payloadJson: string, secret: string): Promise<string> {
  const key = await importHmacKey(secret);
  const signatureBuf = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadJson)
  );
  return toBase64Url(new Uint8Array(signatureBuf));
}

/** Creates a fresh, signed session cookie value with a renewed expiry. */
export async function createSessionValue(secret: string): Promise<string> {
  const payload: SessionPayload = {
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_SECONDS,
  };
  const payloadJson = JSON.stringify(payload);
  const payloadB64 = toBase64Url(new TextEncoder().encode(payloadJson));
  const signatureB64 = await sign(payloadJson, secret);
  return `${payloadB64}.${signatureB64}`;
}

/**
 * Verifies a session cookie value's signature and expiry.
 * Returns true if valid and not expired.
 */
export async function verifySessionValue(
  value: string | undefined | null,
  secret: string
): Promise<boolean> {
  if (!value) return false;
  const parts = value.split(".");
  if (parts.length !== 2) return false;
  const [payloadB64, signatureB64] = parts;

  let payloadJson: string;
  try {
    payloadJson = new TextDecoder().decode(fromBase64Url(payloadB64));
  } catch {
    return false;
  }

  const expectedSignature = await sign(payloadJson, secret);
  if (!timingSafeEqual(expectedSignature, signatureB64)) return false;

  let payload: SessionPayload;
  try {
    payload = JSON.parse(payloadJson) as SessionPayload;
  } catch {
    return false;
  }

  if (typeof payload.exp !== "number") return false;
  return payload.exp > Math.floor(Date.now() / 1000);
}

/** Constant-time string comparison (equal-length strings assumed ASCII). */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

/**
 * Constant-time comparison of the submitted passcode against the configured
 * one. Both are hashed to fixed-length digests first so the comparison time
 * doesn't leak the length of the real passcode either.
 */
export async function passcodeMatches(
  submitted: string,
  expected: string
): Promise<boolean> {
  const digestOf = async (s: string) => {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
    return toBase64Url(new Uint8Array(buf));
  };
  const [a, b] = await Promise.all([digestOf(submitted), digestOf(expected)]);
  return timingSafeEqual(a, b);
}

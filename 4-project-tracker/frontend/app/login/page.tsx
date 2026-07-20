"use client";

import { Suspense, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type Status = "idle" | "submitting" | "error-wrong-passcode" | "error-network" | "error-rate-limited";

const SAFE_RETURN_PATHS = new Set(["/"]);

function resolveReturnTo(raw: string | null): string {
  if (raw && SAFE_RETURN_PATHS.has(raw)) return raw;
  return "/";
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = resolveReturnTo(searchParams.get("returnTo"));

  const [passcode, setPasscode] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const submittingRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const isSubmitting = status === "submitting";
  const isInvalid =
    status === "error-wrong-passcode" ||
    status === "error-network" ||
    status === "error-rate-limited";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submittingRef.current) return; // guard against double-submit
    const trimmed = passcode.trim();
    if (!trimmed) return;

    submittingRef.current = true;
    setStatus("submitting");

    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode: trimmed }),
      });

      if (response.status === 429) {
        setStatus("error-rate-limited");
        return;
      }

      if (response.status === 401) {
        setStatus("error-wrong-passcode");
        setPasscode("");
        // Refocus after the state update so `disabled` clears first.
        requestAnimationFrame(() => inputRef.current?.focus());
        return;
      }

      if (!response.ok) {
        setStatus("error-network");
        return;
      }

      router.push(returnTo);
    } catch {
      setStatus("error-network");
    } finally {
      submittingRef.current = false;
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center font-sans px-4">
      <div className="w-full max-w-sm bg-white/5 backdrop-blur-sm rounded-lg p-6 shadow-sm border border-white/10">
        <h1 className="text-xl font-bold text-center text-white">Todo App</h1>
        <p className="mt-2 mb-4 text-center text-sm text-zinc-400">
          Enter the passcode to access it.
        </p>
        <form onSubmit={handleSubmit} noValidate>
          <div className="flex w-full">
            <label htmlFor="passcode" className="sr-only">
              Passcode
            </label>
            <input
              id="passcode"
              ref={inputRef}
              type="password"
              autoFocus
              autoComplete="off"
              value={passcode}
              disabled={isSubmitting}
              aria-invalid={isInvalid ? "true" : undefined}
              aria-describedby={isInvalid ? "passcode-error" : undefined}
              onChange={(e) => setPasscode(e.target.value)}
              className={`flex-1 w-full p-2 border rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white/5 text-white disabled:opacity-60 ${
                isInvalid
                  ? "border-red-500 focus:ring-red-500"
                  : "border-white/10"
              }`}
            />
            <button
              type="submit"
              disabled={isSubmitting || passcode.trim() === ""}
              className="bg-blue-500 text-white px-4 py-2 rounded-r-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-blue-500/40 disabled:cursor-not-allowed inline-flex items-center gap-2"
            >
              {isSubmitting && (
                <span
                  aria-hidden="true"
                  className="inline-block h-4 w-4 rounded-full border-2 border-white/70 border-t-transparent animate-spin"
                />
              )}
              {isSubmitting ? "Checking…" : "Enter"}
            </button>
          </div>
          <div className="min-h-[1.25rem] text-sm mt-1">
            {status === "error-wrong-passcode" && (
              <p id="passcode-error" role="alert" className="text-red-400">
                Incorrect passcode. Try again.
              </p>
            )}
            {status === "error-network" && (
              <p id="passcode-error" role="alert" className="text-red-400">
                Couldn&apos;t reach the server. Check your connection and try again.
              </p>
            )}
            {status === "error-rate-limited" && (
              <p id="passcode-error" role="alert" className="text-red-400">
                Too many attempts. Try again in a moment.
              </p>
            )}
          </div>
        </form>
        <p className="mt-3 text-center text-sm text-zinc-400">
          Don&apos;t have the passcode?{" "}
          <a
            href="mailto:richardcristhian94@gmail.com?subject=Passcode%20request&body=Hi%20Cristhian%2C%0A%0ACould%20you%20please%20send%20me%20the%20passcode%20for%20the%20AI%20Engineer%20Path%20app%3F%0A%0AThanks%21"
            className="text-blue-500 hover:underline"
          >
            Email me for it
          </a>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

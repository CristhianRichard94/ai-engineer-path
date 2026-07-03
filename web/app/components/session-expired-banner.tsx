"use client";

import Link from "next/link";
import { useState } from "react";

interface SessionExpiredBannerProps {
  /** Current path, used as the `returnTo` target after re-entering the passcode. */
  returnTo: string;
}

/**
 * Dismissible banner shown when a backend call under a proxied route returns
 * 401 (session cookie missing/expired/invalid). Intentionally not a hard
 * redirect so in-progress typed input in the page isn't lost.
 */
export default function SessionExpiredBanner({ returnTo }: SessionExpiredBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div
      role="status"
      className="w-full border-b border-yellow-300 bg-yellow-50 text-yellow-900 dark:border-yellow-800 dark:bg-yellow-950 dark:text-yellow-200 px-4 py-2 text-sm flex items-center justify-between gap-3"
    >
      <Link
        href={`/login?returnTo=${encodeURIComponent(returnTo)}`}
        className="underline focus:outline-none focus:ring-2 focus:ring-yellow-600 rounded"
      >
        Your session expired — re-enter passcode
      </Link>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setDismissed(true)}
        className="shrink-0 rounded px-1 focus:outline-none focus:ring-2 focus:ring-yellow-600"
      >
        ×
      </button>
    </div>
  );
}

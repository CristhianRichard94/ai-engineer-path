"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { fetchReadmeRaw, toRepoFetchError } from "../lib/github";
import type { RepoFetchError } from "../lib/types";

interface ReadmePreviewProps {
  owner: string;
  repo: string;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; error: RepoFetchError }
  | { status: "loaded"; content: string };

function SkeletonBlock({ className }: { className: string }) {
  return <div className={`animate-pulse bg-zinc-200 dark:bg-zinc-700 rounded ${className}`} />;
}

function ErrorBanner({
  error,
  onRetry,
}: {
  error: RepoFetchError;
  onRetry?: () => void;
}) {
  const classesByKind: Record<string, string> = {
    rate_limited:
      "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200",
    not_found:
      "border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300",
    network:
      "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
  };
  return (
    <div
      role="alert"
      className={`rounded-lg border px-3 py-2 text-sm flex items-center justify-between gap-2 ${classesByKind[error.kind]}`}
    >
      <span>{error.message}</span>
      {error.kind === "network" && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="underline shrink-0 focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export default function ReadmePreview({ owner, repo }: ReadmePreviewProps) {
  const [attempt, setAttempt] = useState(0);
  const fetchKey = `${owner}/${repo}/${attempt}`;
  const [state, setState] = useState<{ key: string; result: LoadState }>({
    key: fetchKey,
    result: { status: "loading" },
  });

  // Adjust state during render when the fetch key changes, per React's
  // guidance for resetting state without calling setState synchronously
  // inside a useEffect body.
  const displayState: LoadState =
    state.key === fetchKey ? state.result : { status: "loading" };

  useEffect(() => {
    let cancelled = false;

    fetchReadmeRaw(owner, repo)
      .then((content) => {
        if (!cancelled) setState({ key: fetchKey, result: { status: "loaded", content } });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            key: fetchKey,
            result: { status: "error", error: toRepoFetchError(err) },
          });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchKey]);

  return (
    <div
      className="flex-1 min-h-0 overflow-y-auto p-4"
      aria-busy={displayState.status === "loading"}
    >
      {displayState.status === "loading" && (
        <div className="space-y-2" aria-hidden="true">
          <SkeletonBlock className="h-5 w-1/3" />
          <SkeletonBlock className="h-4 w-full" />
          <SkeletonBlock className="h-4 w-5/6" />
          <SkeletonBlock className="h-4 w-4/6" />
          <SkeletonBlock className="h-4 w-full" />
        </div>
      )}

      {displayState.status === "error" && (
        <ErrorBanner
          error={displayState.error}
          onRetry={
            displayState.error.kind === "network"
              ? () => setAttempt((a) => a + 1)
              : undefined
          }
        />
      )}

      {displayState.status === "loaded" && (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown>{displayState.content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

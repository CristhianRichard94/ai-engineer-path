"use client";

import { useEffect, useState } from "react";
import { fetchRepoMetadata, toRepoFetchError } from "../lib/github";
import type { GithubRepoMetadata, RepoFetchError } from "../lib/types";

interface RepoMetadataProps {
  owner: string;
  repo: string;
  onMetadataLoaded?: (data: GithubRepoMetadata) => void;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; error: RepoFetchError }
  | { status: "loaded"; data: GithubRepoMetadata };

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
  if (error.kind === "rate_limited") {
    return (
      <div
        role="alert"
        className="rounded-lg border px-3 py-2 text-sm border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
      >
        {error.message}
      </div>
    );
  }
  if (error.kind === "not_found") {
    return (
      <div
        role="alert"
        className="rounded-lg border px-3 py-2 text-sm border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
      >
        {error.message}
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="rounded-lg border px-3 py-2 text-sm border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200 flex items-center justify-between gap-2"
    >
      <span>{error.message}</span>
      {onRetry && (
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

export default function RepoMetadata({ owner, repo, onMetadataLoaded }: RepoMetadataProps) {
  const [attempt, setAttempt] = useState(0);
  const fetchKey = `${owner}/${repo}/${attempt}`;
  const [state, setState] = useState<{ key: string; result: LoadState }>({
    key: fetchKey,
    result: { status: "loading" },
  });

  // Adjust state during render when the fetch key changes, per React's
  // guidance for resetting state without an extra effect-driven render
  // (avoids calling setState synchronously inside a useEffect body).
  const displayState: LoadState =
    state.key === fetchKey ? state.result : { status: "loading" };

  useEffect(() => {
    let cancelled = false;

    fetchRepoMetadata(owner, repo)
      .then((data) => {
        if (!cancelled) {
          setState({ key: fetchKey, result: { status: "loaded", data } });
          onMetadataLoaded?.(data);
        }
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
      className="shrink-0 max-h-40 overflow-y-auto p-4"
      aria-busy={displayState.status === "loading"}
    >
      {displayState.status === "loading" && (
        <div className="space-y-2" aria-hidden="true">
          <SkeletonBlock className="h-4 w-3/4" />
          <SkeletonBlock className="h-4 w-1/2" />
          <SkeletonBlock className="h-4 w-2/3" />
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
        <dl className="text-sm text-zinc-700 dark:text-zinc-300 space-y-1">
          <div>
            <dt className="sr-only">Description</dt>
            <dd>{displayState.data.description || "No description provided."}</dd>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-zinc-500 dark:text-zinc-400">
            <span>
              <dt className="sr-only">Stars</dt>
              <dd className="inline">★ {displayState.data.stargazers_count.toLocaleString()}</dd>
            </span>
            <span>
              <dt className="sr-only">Default branch</dt>
              <dd className="inline">Branch: {displayState.data.default_branch}</dd>
            </span>
            {displayState.data.language && (
              <span>
                <dt className="sr-only">Primary language</dt>
                <dd className="inline">{displayState.data.language}</dd>
              </span>
            )}
          </div>
        </dl>
      )}
    </div>
  );
}

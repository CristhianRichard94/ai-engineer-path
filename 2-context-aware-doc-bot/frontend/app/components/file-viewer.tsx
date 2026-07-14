"use client";

import { useEffect, useState } from "react";
import { fetchFileRaw, toRepoFetchError } from "../lib/github";
import type { RepoFetchError } from "../lib/types";

interface FileViewerProps {
  owner: string;
  repo: string;
  branch: string;
  path: string;
  onClose: () => void;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; error: RepoFetchError }
  | { status: "loaded"; content: string };

export default function FileViewer({ owner, repo, branch, path, onClose }: FileViewerProps) {
  const [state, setState] = useState<{ key: string; result: LoadState }>({
    key: path,
    result: { status: "loading" },
  });

  const displayState: LoadState =
    state.key === path ? state.result : { status: "loading" };

  useEffect(() => {
    let cancelled = false;

    fetchFileRaw(owner, repo, path, branch)
      .then((content) => {
        if (!cancelled) setState({ key: path, result: { status: "loaded", content } });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({ key: path, result: { status: "error", error: toRepoFetchError(err) } });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [owner, repo, path, branch]);

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-black">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-200 dark:border-zinc-800 px-3 py-2">
        <span className="truncate text-sm font-mono text-zinc-700 dark:text-zinc-300">
          {path}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-md px-2 py-1 text-sm text-zinc-500 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Close
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {displayState.status === "loading" && (
          <div className="p-4 space-y-2" aria-hidden="true">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-4 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700"
                style={{ width: `${50 + ((i * 17) % 40)}%` }}
              />
            ))}
          </div>
        )}

        {displayState.status === "error" && (
          <div role="alert" className="m-3 rounded-lg border px-3 py-2 text-sm border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
            {displayState.error.message}
          </div>
        )}

        {displayState.status === "loaded" && (
          <pre className="p-4 text-xs font-mono whitespace-pre overflow-auto text-zinc-800 dark:text-zinc-200">
            <code>{displayState.content}</code>
          </pre>
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { fetchDirectoryContents, toRepoFetchError } from "../lib/github";
import type { GithubContentItem, RepoFetchError } from "../lib/types";

interface FileTreeProps {
  owner: string;
  repo: string;
  branch: string;
}

interface TreeNodeState {
  item: GithubContentItem;
  depth: number;
  expanded: boolean;
  loading: boolean;
  error: RepoFetchError | null;
  children: GithubContentItem[] | null;
}

function SkeletonRows() {
  return (
    <div className="p-2 space-y-1" aria-hidden="true">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="animate-pulse bg-zinc-200 dark:bg-zinc-700 rounded h-5"
          style={{ width: `${60 + ((i * 13) % 30)}%` }}
        />
      ))}
    </div>
  );
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
      className={`rounded-lg border px-3 py-2 m-2 text-sm flex items-center justify-between gap-2 ${classesByKind[error.kind]}`}
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

export default function FileTree({ owner, repo, branch }: FileTreeProps) {
  const [rootAttempt, setRootAttempt] = useState(0);
  const rootKey = `${owner}/${repo}/${branch}/${rootAttempt}`;

  const [rootResult, setRootResult] = useState<{
    key: string;
    loading: boolean;
    error: RepoFetchError | null;
  }>({ key: rootKey, loading: true, error: null });

  const [rootItems, setRootItems] = useState<GithubContentItem[]>([]);

  // Flattened visible node list, keyed by path.
  const [nodes, setNodes] = useState<Map<string, TreeNodeState>>(new Map());
  const [order, setOrder] = useState<string[]>([]);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Adjust state during render when the fetch key changes, per React's
  // guidance for resetting state without calling setState synchronously
  // inside a useEffect body.
  const rootLoading = rootResult.key === rootKey ? rootResult.loading : true;
  const rootError = rootResult.key === rootKey ? rootResult.error : null;

  useEffect(() => {
    let cancelled = false;

    fetchDirectoryContents(owner, repo, "", branch)
      .then(async (items) => {
        if (cancelled) return;
        setRootItems(items);
        setRootResult({ key: rootKey, loading: false, error: null });

        // Root's first-level children are rendered immediately (no extra
        // fetch needed — they came back with the root response). They start
        // collapsed; each directory's own children are lazily fetched only
        // when the user expands it via toggleNode/loadChildren.
        const initialNodes = new Map<string, TreeNodeState>();
        const initialOrder: string[] = [];

        for (const item of items) {
          initialNodes.set(item.path, {
            item,
            depth: 0,
            expanded: false,
            loading: false,
            error: null,
            children: null,
          });
          initialOrder.push(item.path);
        }

        setNodes(initialNodes);
        setOrder(initialOrder);
      })
      .catch((err) => {
        if (!cancelled) {
          setRootResult({ key: rootKey, loading: false, error: toRepoFetchError(err) });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootKey]);

  async function loadChildren(path: string, depth: number) {
    setNodes((prev) => {
      const next = new Map(prev);
      const existing = next.get(path);
      if (existing) {
        next.set(path, { ...existing, loading: true, error: null });
      }
      return next;
    });

    try {
      const children = await fetchDirectoryContents(owner, repo, path, branch);

      setNodes((prev) => {
        const next = new Map(prev);
        const existing = next.get(path);
        if (existing) {
          next.set(path, {
            ...existing,
            loading: false,
            error: null,
            children,
          });
        }
        for (const child of children) {
          if (!next.has(child.path)) {
            next.set(child.path, {
              item: child,
              depth,
              expanded: false,
              loading: false,
              error: null,
              children: null,
            });
          }
        }
        return next;
      });

      setOrder((prev) => {
        const idx = prev.indexOf(path);
        if (idx === -1) return prev;
        const already = new Set(prev);
        const newPaths = children.map((c) => c.path).filter((p) => !already.has(p));
        if (newPaths.length === 0) return prev;
        const next = prev.slice();
        next.splice(idx + 1, 0, ...newPaths);
        return next;
      });
    } catch (err) {
      setNodes((prev) => {
        const next = new Map(prev);
        const existing = next.get(path);
        if (existing) {
          next.set(path, {
            ...existing,
            loading: false,
            error: toRepoFetchError(err),
          });
        }
        return next;
      });
    }
  }

  function toggleNode(path: string) {
    const node = nodes.get(path);
    if (!node || node.item.type !== "dir") return;

    const willExpand = !node.expanded;
    setNodes((prev) => {
      const next = new Map(prev);
      next.set(path, { ...node, expanded: willExpand });
      return next;
    });

    if (willExpand && node.children === null && !node.loading) {
      void loadChildren(path, node.depth + 1);
    }

    if (!willExpand) {
      // Collapsing: remove descendant paths from the visible order list
      // (cache stays intact on the node itself for instant re-expand).
      setOrder((prev) => {
        const descendantPrefix = `${path}/`;
        return prev.filter((p) => p === path || !p.startsWith(descendantPrefix));
      });
    }
  }

  // Visible rows: a node is visible if it's a first-level item, or if every
  // ancestor directory above it is expanded.
  function isVisible(path: string): boolean {
    const node = nodes.get(path);
    if (!node) return false;
    if (node.depth === 0) return true;
    const parentPath = path.slice(0, path.lastIndexOf("/"));
    const parent = nodes.get(parentPath);
    if (!parent || !parent.expanded) return false;
    return isVisible(parentPath);
  }

  const visibleOrder = order.filter(isVisible);

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>, path: string) {
    const node = nodes.get(path);
    if (!node) return;

    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (node.item.type === "dir") {
        toggleNode(path);
      }
      return;
    }

    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const idx = visibleOrder.indexOf(path);
      const nextIdx = e.key === "ArrowDown" ? idx + 1 : idx - 1;
      const nextPath = visibleOrder[nextIdx];
      if (nextPath) {
        rowRefs.current.get(nextPath)?.focus();
      }
    }
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-2" aria-busy={rootLoading}>
      {rootLoading && <SkeletonRows />}

      {rootError && (
        <ErrorBanner
          error={rootError}
          onRetry={
            rootError.kind === "network" ? () => setRootAttempt((a) => a + 1) : undefined
          }
        />
      )}

      {!rootLoading && !rootError && rootItems.length === 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400 p-2">
          This repository has no files.
        </p>
      )}

      {!rootLoading && !rootError && visibleOrder.length > 0 && (
        <div role="tree" aria-label="Repository file tree">
          {visibleOrder.map((path) => {
            const node = nodes.get(path);
            if (!node) return null;
            const isDir = node.item.type === "dir";
            return (
              <div key={path}>
                <div
                  ref={(el) => {
                    if (el) rowRefs.current.set(path, el);
                    else rowRefs.current.delete(path);
                  }}
                  role="treeitem"
                  aria-expanded={isDir ? node.expanded : undefined}
                  aria-selected={isDir ? node.expanded : false}
                  tabIndex={0}
                  onClick={() => isDir && toggleNode(path)}
                  onKeyDown={(e) => handleKeyDown(e, path)}
                  style={{ paddingLeft: 8 + node.depth * 16 }}
                  className={`flex items-center gap-1.5 px-2 py-2.5 rounded-md text-sm text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 cursor-pointer min-h-[44px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset ${
                    isDir && node.expanded
                      ? "bg-blue-50 dark:bg-blue-950 text-blue-800 dark:text-blue-200"
                      : ""
                  }`}
                >
                  {isDir ? (
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className={`h-3.5 w-3.5 shrink-0 transition-transform ${
                        node.expanded ? "rotate-90" : ""
                      }`}
                    >
                      <path
                        fillRule="evenodd"
                        d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  )}
                  <span className="truncate">{node.item.name}</span>
                  {node.loading && (
                    <span
                      aria-hidden="true"
                      className="inline-block h-3 w-3 rounded-full border-2 border-current border-t-transparent animate-spin shrink-0 ml-1"
                    />
                  )}
                </div>
                {node.error && (
                  <div style={{ paddingLeft: 8 + (node.depth + 1) * 16 }}>
                    <ErrorBanner
                      error={node.error}
                      onRetry={
                        node.error.kind === "network"
                          ? () => loadChildren(path, node.depth + 1)
                          : undefined
                      }
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

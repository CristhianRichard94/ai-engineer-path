"use client";

import { useState } from "react";
import RepoMetadata from "./repo-metadata";
import FileTree from "./file-tree";
import ReadmePreview from "./readme-preview";
import type { GithubRepoMetadata } from "../lib/types";

interface RepoPanelProps {
  owner: string;
  repo: string;
}

/**
 * Repo Panel composes three sub-regions (metadata, file tree, README).
 * Metadata and README own fully independent fetches/loading/error state.
 *
 * The file tree needs `default_branch` to query `contents` with `?ref=`.
 * Rather than fetching metadata a second time just to learn the branch, we
 * reuse RepoMetadata's own successful fetch: it reports the loaded data back
 * up via `onMetadataLoaded`, and FileTree waits (showing the existing
 * loading UI) until that branch is known. If RepoMetadata's fetch fails, the
 * branch never resolves and FileTree simply never renders — RepoMetadata's
 * own error banner already communicates that the repo data couldn't load.
 */
export default function RepoPanel({ owner, repo }: RepoPanelProps) {
  const repoKey = `${owner}/${repo}`;
  const [branchState, setBranchState] = useState<{ key: string; branch: string | null }>({
    key: repoKey,
    branch: null,
  });

  // Adjust state during render when owner/repo changes, per React's guidance
  // for resetting state without calling setState synchronously inside a
  // useEffect body.
  const branch = branchState.key === repoKey ? branchState.branch : null;

  function handleMetadataLoaded(data: GithubRepoMetadata) {
    setBranchState({ key: repoKey, branch: data.default_branch });
  }

  return (
    <div className="flex flex-col h-full">
      <RepoMetadata owner={owner} repo={repo} onMetadataLoaded={handleMetadataLoaded} />
      <div className="border-t border-zinc-200 dark:border-zinc-800 flex-1 min-h-0 flex flex-col">
        {branch !== null && <FileTree owner={owner} repo={repo} branch={branch} />}
      </div>
      <div className="border-t border-zinc-200 dark:border-zinc-800 flex-1 min-h-0 flex flex-col">
        <ReadmePreview owner={owner} repo={repo} />
      </div>
    </div>
  );
}

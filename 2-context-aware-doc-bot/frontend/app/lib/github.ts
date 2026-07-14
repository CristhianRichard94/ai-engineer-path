// Client-side GitHub REST API client (unauthenticated, ~60 req/hour budget).
// Avoid recursive `git/trees`; use lazy per-directory `contents` calls instead.

import type {
  GithubContentItem,
  GithubRepoMetadata,
  RepoFetchError,
} from "./types";

const GITHUB_API_BASE = "https://api.github.com";

class GithubApiError extends Error {
  kind: RepoFetchError["kind"];

  constructor(kind: RepoFetchError["kind"], message: string) {
    super(message);
    this.kind = kind;
    this.name = "GithubApiError";
  }
}

// SECURITY WARNING: NEXT_PUBLIC_GITHUB_TOKEN is embedded in the public JS bundle
// and is visible to anyone who opens DevTools. Use a fine-grained token scoped to
// read-only public repo access only. Never use a token with write permissions or
// private repo access.
function getAuthHeaders(): Record<string, string> {
  const token = process.env.NEXT_PUBLIC_GITHUB_TOKEN;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function githubFetch(path: string, init?: RequestInit): Promise<Response> {
  const authHeaders = getAuthHeaders();
  const mergedInit: RequestInit = {
    ...init,
    headers: {
      ...authHeaders,
      ...(init?.headers as Record<string, string> | undefined),
    },
  };

  let response: Response;
  try {
    response = await fetch(`${GITHUB_API_BASE}${path}`, mergedInit);
  } catch {
    throw new GithubApiError("network", "Network error while contacting GitHub.");
  }

  if (response.status === 403 && response.headers.get("x-ratelimit-remaining") === "0") {
    throw new GithubApiError(
      "rate_limited",
      "GitHub API rate limit reached. Please try again later."
    );
  }

  if (response.status === 404) {
    throw new GithubApiError(
      "not_found",
      "Repository not found. It may be private or may not exist."
    );
  }

  if (!response.ok) {
    throw new GithubApiError("network", `GitHub API error (${response.status}).`);
  }

  return response;
}

export async function fetchRepoMetadata(
  owner: string,
  repo: string
): Promise<GithubRepoMetadata> {
  const response = await githubFetch(`/repos/${owner}/${repo}`);
  const data = await response.json();
  return {
    description: data.description ?? null,
    stargazers_count: data.stargazers_count ?? 0,
    default_branch: data.default_branch ?? "main",
    language: data.language ?? null,
  };
}

export async function fetchDirectoryContents(
  owner: string,
  repo: string,
  path: string,
  ref: string
): Promise<GithubContentItem[]> {
  const encodedPath = path
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
  const query = ref ? `?ref=${encodeURIComponent(ref)}` : "";
  const response = await githubFetch(
    `/repos/${owner}/${repo}/contents/${encodedPath}${query}`
  );
  const data = await response.json();
  if (!Array.isArray(data)) {
    // A single file was returned (path pointed at a file, not a dir).
    return [];
  }
  return (data as GithubContentItem[])
    .slice()
    .sort((a, b) => {
      if (a.type === b.type) return a.name.localeCompare(b.name);
      return a.type === "dir" ? -1 : 1;
    });
}

export async function fetchReadmeRaw(owner: string, repo: string): Promise<string> {
  const response = await githubFetch(`/repos/${owner}/${repo}/readme`, {
    headers: {
      Accept: "application/vnd.github.raw",
    },
  });
  return response.text();
}

export async function fetchFileRaw(
  owner: string,
  repo: string,
  path: string,
  ref: string
): Promise<string> {
  const encodedPath = path
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
  const response = await githubFetch(
    `/repos/${owner}/${repo}/contents/${encodedPath}?ref=${encodeURIComponent(ref)}`,
    { headers: { Accept: "application/vnd.github.raw" } }
  );
  return response.text();
}

export function toRepoFetchError(err: unknown): RepoFetchError {
  if (err instanceof GithubApiError) {
    return { kind: err.kind, message: err.message };
  }
  return { kind: "network", message: "Something went wrong. Please try again." };
}

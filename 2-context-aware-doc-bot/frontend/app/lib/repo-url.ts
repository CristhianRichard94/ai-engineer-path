// Shared GitHub repo URL parsing/validation utility.
// Used both for client-side form validation and for deriving owner/repo
// used in GitHub API calls and backend indexing requests.

import type { ParsedRepoUrl } from "./types";

/**
 * Parses a GitHub repository URL, tolerating:
 * - trailing slash
 * - trailing `.git` suffix
 * - extra path segments (e.g. `/tree/branch`, `/blob/main/file.ts`)
 *
 * Returns null if the URL is empty, malformed, or not a github.com host.
 */
export function parseRepoUrl(input: string): ParsedRepoUrl | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  let url: URL;
  try {
    // Allow bare host without protocol to fail naturally; require explicit
    // scheme per spec ("Valid URL shape: https://github.com/{owner}/{repo}").
    url = new URL(trimmed);
  } catch {
    return null;
  }

  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  if (url.hostname.toLowerCase() !== "github.com") return null;

  const segments = url.pathname.split("/").filter(Boolean);
  if (segments.length < 2) return null;

  const owner = segments[0];
  let repo = segments[1];

  // Strip trailing `.git` suffix.
  repo = repo.replace(/\.git$/i, "");

  if (!owner || !repo) return null;

  // Basic GitHub-safe segment validation (letters, digits, dot, dash, underscore).
  const validSegment = /^[A-Za-z0-9._-]+$/;
  if (!validSegment.test(owner) || !validSegment.test(repo)) return null;

  return {
    owner,
    repo,
    normalized: `https://github.com/${owner}/${repo}`,
  };
}

export function isValidRepoUrl(input: string): boolean {
  return parseRepoUrl(input) !== null;
}

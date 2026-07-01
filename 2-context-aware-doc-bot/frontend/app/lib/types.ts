// Shared types for the context-aware-doc-bot frontend.

// ---------- Repo identity ----------

export interface ParsedRepoUrl {
  owner: string;
  repo: string;
  /** Normalized canonical URL, e.g. https://github.com/{owner}/{repo} */
  normalized: string;
}

// ---------- Backend: /api/index ----------

export interface IndexDispatchedResponse {
  job_id: string;
  commit: string;
}

export interface IndexAlreadyIndexedResponse {
  status: "already_indexed";
  commit: string;
}

export type IndexPostResponse =
  | { kind: "dispatched"; job_id: string; commit: string }
  | { kind: "already_indexed"; commit: string };

export type IndexJobStatus = "pending" | "started" | "done" | "failure";

export interface IndexJobStatusResponse {
  job_id: string;
  status: IndexJobStatus;
  error?: string;
  commit?: string;
  [key: string]: unknown;
}

// ---------- Backend: /api/prompt/stream ----------

export interface StreamDeltaEvent {
  delta: string;
}

export interface StreamDoneEvent {
  done: true;
}

export interface StreamErrorEvent {
  error: string;
}

export type StreamEvent = StreamDeltaEvent | StreamDoneEvent | StreamErrorEvent;

// ---------- Chat domain ----------

export type ChatRole = "user" | "assistant";

export type AssistantErrorKind = "retry" | "reindex" | null;

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** True while an assistant message is actively streaming tokens. */
  streaming?: boolean;
  /** True once the "thinking" placeholder should show (no delta received yet). */
  pending?: boolean;
  /** Set when this assistant message ended in an error state. */
  error?: AssistantErrorKind;
  errorMessage?: string;
  /** The prompt that produced this assistant message (needed for retry). */
  sourcePrompt?: string;
}

// ---------- GitHub API ----------

export interface GithubRepoMetadata {
  description: string | null;
  stargazers_count: number;
  default_branch: string;
  language: string | null;
}

export interface GithubContentItem {
  name: string;
  path: string;
  sha: string;
  size: number;
  type: "file" | "dir" | "symlink" | "submodule";
}

export type RepoFetchErrorKind = "rate_limited" | "not_found" | "network" | null;

export interface RepoFetchError {
  kind: Exclude<RepoFetchErrorKind, null>;
  message: string;
}

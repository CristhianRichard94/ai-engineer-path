"use client";

import { useEffect, useRef, useState } from "react";
import RepoForm from "./components/repo-form";
import StatusStrip, { StatusStripVariant } from "./components/status-strip";
import RepoPanel from "./components/repo-panel";
import ChatPanel from "./components/chat-panel";
import { getIndexStatus, postIndex, ApiError } from "./lib/api";
import { parseRepoUrl } from "./lib/repo-url";
import type { ChatMessage, IndexJobStatus } from "./lib/types";
import SessionExpiredBanner from "../components/session-expired-banner";
import Link from "next/link";

type Phase = "entry" | "indexing" | "ready";

const POLL_INTERVAL_MS = 2000;
const MAX_CONSECUTIVE_POLL_FAILURES = 4;

interface ActiveRepo {
  owner: string;
  repo: string;
  url: string;
  commit: string;
}

export default function DocBotPage() {
  const [phase, setPhase] = useState<Phase>("entry");
  const [urlInput, setUrlInput] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const [indexVariant, setIndexVariant] = useState<StatusStripVariant>("pending");
  const [indexMessage, setIndexMessage] = useState("");
  const [indexFading, setIndexFading] = useState(false);

  const [activeRepo, setActiveRepo] = useState<ActiveRepo | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // Pending switch-repo confirmation (when chat history exists).
  const [pendingSwitchUrl, setPendingSwitchUrl] = useState<string | null>(null);

  // Below the `lg` breakpoint, Repo/Chat panels are shown as tabs instead of
  // side-by-side columns.
  const [mobileTab, setMobileTab] = useState<"repo" | "chat">("repo");

  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollFailureCountRef = useRef(0);
  const currentJobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  function clearPoll() {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }

  function startIndexing(url: string) {
    const parsed = parseRepoUrl(url);
    if (!parsed) return; // RepoForm already validated; defensive guard.

    currentJobUrlRef.current = url;
    pollFailureCountRef.current = 0;
    setSubmitError(null);
    setPhase("indexing");
    setIndexVariant("pending");
    setIndexMessage("Queued — waiting to start…");

    postIndex(url)
      .then((result) => {
        if (currentJobUrlRef.current !== url) return; // superseded

        if (result.kind === "already_indexed") {
          setActiveRepo({
            owner: parsed.owner,
            repo: parsed.repo,
            url: parsed.normalized,
            commit: result.commit,
          });
          setToast("Repo already indexed — showing cached results.");
          setPhase("ready");
          window.setTimeout(() => setToast(null), 3000);
          return;
        }

        pollJob(result.job_id, url, parsed);
      })
      .catch((err) => {
        if (currentJobUrlRef.current !== url) return;
        if (err instanceof ApiError && err.status === 401) {
          setSessionExpired(true);
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Network error — could not reach the server.";
        // Network/5xx error on initial POST: inline error near input, button
        // returns to idle, keep what user typed.
        setSubmitError(message);
        setPhase("entry");
      });
  }

  function pollJob(
    jobId: string,
    url: string,
    parsed: { owner: string; repo: string; normalized: string }
  ) {
    getIndexStatus(jobId)
      .then((status) => {
        if (currentJobUrlRef.current !== url) return;
        pollFailureCountRef.current = 0;
        handleJobStatus(status.status, status, url, parsed, jobId);
      })
      .catch((err) => {
        if (currentJobUrlRef.current !== url) return;
        if (err instanceof ApiError && err.status === 401) {
          setSessionExpired(true);
        }
        pollFailureCountRef.current += 1;
        if (pollFailureCountRef.current >= MAX_CONSECUTIVE_POLL_FAILURES) {
          setIndexVariant("failure");
          setIndexMessage(
            "Lost connection while checking indexing status. Please retry."
          );
          return;
        }
        pollTimeoutRef.current = setTimeout(
          () => pollJob(jobId, url, parsed),
          POLL_INTERVAL_MS
        );
      });
  }

  function handleJobStatus(
    status: IndexJobStatus,
    fullStatus: { error?: string; commit?: string },
    url: string,
    parsed: { owner: string; repo: string; normalized: string },
    jobId: string
  ) {
    if (status === "pending") {
      setIndexVariant("pending");
      setIndexMessage("Queued — waiting to start…");
      pollTimeoutRef.current = setTimeout(
        () => pollJob(jobId, url, parsed),
        POLL_INTERVAL_MS
      );
      return;
    }

    if (status === "started") {
      setIndexVariant("started");
      setIndexMessage("Indexing repo — cloning, chunking, and embedding…");
      pollTimeoutRef.current = setTimeout(
        () => pollJob(jobId, url, parsed),
        POLL_INTERVAL_MS
      );
      return;
    }

    if (status === "done") {
      clearPoll();
      setIndexVariant("success");
      setIndexMessage("Indexing complete!");
      setActiveRepo({
        owner: parsed.owner,
        repo: parsed.repo,
        url: parsed.normalized,
        commit: fullStatus.commit || "",
      });
      // Brief success flash, fades before ready layout mounts.
      window.setTimeout(() => setIndexFading(true), 200);
      window.setTimeout(() => {
        setPhase("ready");
        setIndexFading(false);
      }, 1800);
      return;
    }

    if (status === "failure") {
      clearPoll();
      setIndexVariant("failure");
      setIndexMessage(fullStatus.error || "Indexing failed. Please try again.");
    }
  }

  function handleSubmitFromEntry(url: string) {
    startIndexing(url);
  }

  function handleRetryFromStrip() {
    if (currentJobUrlRef.current) {
      startIndexing(currentJobUrlRef.current);
    }
  }

  function handleTopZoneSubmit(url: string) {
    if (activeRepo && messages.length > 0) {
      // Lightweight inline confirmation before clearing conversation.
      setPendingSwitchUrl(url);
      return;
    }
    proceedWithSwitch(url);
  }

  function proceedWithSwitch(url: string) {
    setMessages([]);
    setActiveRepo(null);
    setToast(null);
    setPendingSwitchUrl(null);
    startIndexing(url);
  }

  function cancelSwitch() {
    setPendingSwitchUrl(null);
  }

  const isReady = phase === "ready" && activeRepo !== null;

  return (
    <div className="flex flex-col flex-1">
      {sessionExpired && <SessionExpiredBanner returnTo="/docbot" />}

      <div
        className={`flex flex-col flex-1 items-center font-sans ${
          isReady ? "" : "justify-center"
        }`}
      >
        {!isReady && (
          <main className="flex flex-1 w-full max-w-3xl flex-col items-center py-16 px-4 sm:py-24 sm:px-16">
            <Link
              href="/"
              className="self-start mb-4 text-sm text-blue-300 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              ← Back to apps
            </Link>
            <h1 className="text-4xl font-bold mb-3">Context-Aware Doc Bot</h1>
            <p className="text-base text-zinc-600 dark:text-zinc-400 mb-8">
              Index a public GitHub repository, then ask questions about its code
              and docs.
            </p>

            <RepoForm
              value={urlInput}
              onValueChange={(v) => {
                setUrlInput(v);
                if (submitError) setSubmitError(null);
              }}
              onSubmit={handleSubmitFromEntry}
              busy={phase === "indexing"}
              submitError={submitError}
            />

            {phase === "indexing" && (
              <div className="w-full mt-6">
                <StatusStrip
                  variant={indexVariant}
                  message={indexMessage}
                  onRetry={indexVariant === "failure" ? handleRetryFromStrip : undefined}
                  fading={indexFading}
                />
              </div>
            )}
          </main>
        )}

        {isReady && activeRepo && (
          <div className="flex flex-col w-full max-w-6xl flex-1">
            <div className="border-b border-zinc-200 dark:border-zinc-800 px-4 py-3 sm:px-6 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
              <Link
                href="/"
                className="text-sm text-blue-300 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded shrink-0"
              >
                ← Back to apps
              </Link>
              <div className="flex-1">
                <RepoForm
                  value={urlInput}
                  onValueChange={(v) => {
                    setUrlInput(v);
                    if (submitError) setSubmitError(null);
                  }}
                  onSubmit={handleTopZoneSubmit}
                  busy={false}
                  submitError={submitError}
                  compact
                />
              </div>
              <div className="flex items-center gap-2 text-sm shrink-0">
                <span className="font-medium">
                  {activeRepo.owner}/{activeRepo.repo}
                </span>
                {activeRepo.commit && (
                  <span className="font-mono text-xs bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                    {activeRepo.commit.slice(0, 7)}
                  </span>
                )}
              </div>
            </div>

            {toast && (
              <div className="px-4 pt-3 sm:px-6">
                <div className="rounded-lg border px-4 py-2 text-sm border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                  {toast}
                </div>
              </div>
            )}

            {pendingSwitchUrl && (
              <div className="px-4 pt-3 sm:px-6">
                <div
                  role="alertdialog"
                  aria-label="Confirm switching repository"
                  className="rounded-lg border px-4 py-3 text-sm border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200 flex flex-col sm:flex-row sm:items-center gap-3"
                >
                  <span className="flex-1">
                    Switching repos will clear your current conversation. Continue?
                  </span>
                  <div className="flex gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => proceedWithSwitch(pendingSwitchUrl)}
                      className="bg-amber-600 text-white px-3 py-1.5 rounded-md hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2"
                    >
                      Switch repo
                    </button>
                    <button
                      type="button"
                      onClick={cancelSwitch}
                      className="px-3 py-1.5 rounded-md border border-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Tabs shown only below the `lg` breakpoint. */}
            <div
              role="tablist"
              aria-label="Panels"
              className="flex lg:hidden border-b border-zinc-200 dark:border-zinc-800 px-4 sm:px-6"
            >
              <button
                type="button"
                role="tab"
                aria-selected={mobileTab === "repo"}
                aria-controls="panel-repo"
                id="tab-repo"
                onClick={() => setMobileTab("repo")}
                className={`px-4 py-2 text-sm font-medium border-b-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  mobileTab === "repo"
                    ? "border-blue-500 text-blue-700 dark:text-blue-300"
                    : "border-transparent text-zinc-500 dark:text-zinc-400"
                }`}
              >
                Repo
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mobileTab === "chat"}
                aria-controls="panel-chat"
                id="tab-chat"
                onClick={() => setMobileTab("chat")}
                className={`px-4 py-2 text-sm font-medium border-b-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  mobileTab === "chat"
                    ? "border-blue-500 text-blue-700 dark:text-blue-300"
                    : "border-transparent text-zinc-500 dark:text-zinc-400"
                }`}
              >
                Chat
              </button>
            </div>

            <div className="flex flex-1 min-h-0 flex-col lg:flex-row">
              <div
                id="panel-repo"
                role="tabpanel"
                aria-labelledby="tab-repo"
                className={`${mobileTab === "repo" ? "flex" : "hidden"} lg:flex lg:w-[46%] lg:max-w-md border-r-0 lg:border-r border-zinc-200 dark:border-zinc-800 flex-col min-h-0 flex-1 lg:flex-initial`}
              >
                <RepoPanel owner={activeRepo.owner} repo={activeRepo.repo} />
              </div>
              <div
                id="panel-chat"
                role="tabpanel"
                aria-labelledby="tab-chat"
                className={`${mobileTab === "chat" ? "flex" : "hidden"} lg:flex flex-1 min-h-0 flex-col p-2 sm:p-4`}
              >
                <ChatPanel
                  repoUrl={activeRepo.url}
                  messages={messages}
                  onMessagesChange={(updater) => setMessages((prev) => updater(prev))}
                  onUnauthorized={() => setSessionExpired(true)}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

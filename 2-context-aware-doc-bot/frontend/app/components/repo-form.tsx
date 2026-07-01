"use client";

import { useId, useState } from "react";
import { isValidRepoUrl } from "../lib/repo-url";

interface RepoFormProps {
  /** Controlled value so the parent can keep "what user typed" across errors. */
  value: string;
  onValueChange: (value: string) => void;
  /** Called with a URL that has already passed client-side validation. */
  onSubmit: (url: string) => void;
  /** True while an index job is in flight (input becomes read-only, not disabled). */
  busy: boolean;
  /** Inline error surfaced from a failed submit attempt (network/5xx on POST /api/index). */
  submitError?: string | null;
  /** Compact variant used in the ready-state top zone. */
  compact?: boolean;
}

export default function RepoForm({
  value,
  onValueChange,
  onSubmit,
  busy,
  submitError,
  compact = false,
}: RepoFormProps) {
  const [touched, setTouched] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = useId();

  const showValidationError = touched && validationError;
  const showError = showValidationError || submitError;

  function validate(candidate: string): string | null {
    const trimmed = candidate.trim();
    if (!trimmed) return "Please enter a GitHub repository URL.";
    if (!isValidRepoUrl(trimmed)) {
      return "Enter a valid GitHub repo URL, e.g. https://github.com/owner/repo.";
    }
    return null;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    attemptSubmit();
  }

  function attemptSubmit() {
    if (busy) return; // guard against duplicate submits while a job is in flight
    setTouched(true);
    const error = validate(value);
    setValidationError(error);
    if (error) return;
    onSubmit(value.trim());
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      // Block Enter-to-submit while read-only/busy, not just relying on the
      // button's disabled state.
      e.preventDefault();
      if (busy) return;
      attemptSubmit();
    }
  }

  const inputBaseClasses =
    "flex-1 w-full p-2 border border-gray-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:border-gray-700 dark:text-white";
  const inputInvalidClasses = "border-red-500 focus:ring-red-500 dark:border-red-500";
  const inputReadOnlyClasses = "cursor-text bg-gray-50 dark:bg-gray-900/60 select-text";

  const inputClasses = [
    inputBaseClasses,
    showError ? inputInvalidClasses : "",
    busy ? inputReadOnlyClasses : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <form
      onSubmit={handleSubmit}
      className={compact ? "w-full" : "w-full"}
      noValidate
    >
      <div className="flex w-full">
        <label htmlFor={inputId} className="sr-only">
          GitHub repository URL
        </label>
        <input
          id={inputId}
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://github.com/owner/repo"
          value={value}
          readOnly={busy}
          aria-invalid={showError ? "true" : undefined}
          aria-describedby={showError ? errorId : undefined}
          onChange={(e) => onValueChange(e.target.value)}
          onBlur={() => setTouched(true)}
          onKeyDown={handleKeyDown}
          className={inputClasses}
        />
        <button
          type="submit"
          disabled={busy}
          className="bg-blue-500 text-white px-4 py-2 rounded-r-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-blue-500/40 disabled:text-white/70 disabled:cursor-not-allowed cursor-pointer disabled:cursor-wait inline-flex items-center gap-2"
        >
          {busy && (
            <span
              aria-hidden="true"
              className="inline-block h-4 w-4 rounded-full border-2 border-white/70 border-t-transparent animate-spin"
            />
          )}
          {busy ? "Indexing…" : "Index repo"}
        </button>
      </div>
      <div className="min-h-[1.25rem] text-sm mt-1">
        {showError ? (
          <p id={errorId} role="alert" className="text-red-600 dark:text-red-400 flex items-center gap-1">
            <svg
              aria-hidden="true"
              className="h-3.5 w-3.5 shrink-0"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l6.28 11.163c.75 1.334-.213 2.988-1.742 2.988H3.72c-1.53 0-2.492-1.654-1.743-2.988l6.28-11.163zM11 14a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V7a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {showValidationError ? validationError : submitError}
          </p>
        ) : (
          <p className="text-zinc-500 dark:text-zinc-400">
            Paste a public GitHub repository URL to get started.
          </p>
        )}
      </div>
    </form>
  );
}

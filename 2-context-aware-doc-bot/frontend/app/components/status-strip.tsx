"use client";

export type StatusStripVariant =
  | "pending"
  | "started"
  | "success"
  | "already_indexed"
  | "failure";

interface StatusStripProps {
  variant: StatusStripVariant;
  message: string;
  onRetry?: () => void;
  /** Applies a fade-out transition, used for the brief success flash. */
  fading?: boolean;
}

const VARIANT_CLASSES: Record<StatusStripVariant, string> = {
  pending:
    "border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300",
  started:
    "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200",
  success:
    "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950 dark:text-green-200",
  already_indexed:
    "border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300",
  failure:
    "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
};

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin shrink-0"
    />
  );
}

export default function StatusStrip({
  variant,
  message,
  onRetry,
  fading = false,
}: StatusStripProps) {
  const isFailure = variant === "failure";
  const showSpinner = variant === "pending" || variant === "started";

  return (
    <div
      role={isFailure ? "alert" : "status"}
      aria-live={isFailure ? undefined : "polite"}
      className={`rounded-lg border px-4 py-3 flex items-center gap-3 text-sm transition-opacity duration-[1800ms] ${VARIANT_CLASSES[variant]} ${
        fading ? "opacity-0" : "opacity-100"
      }`}
    >
      {showSpinner && <Spinner />}
      <span className="flex-1">{message}</span>
      {isFailure && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="bg-red-600 text-white px-3 py-1.5 rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-red-950 shrink-0"
        >
          Retry
        </button>
      )}
    </div>
  );
}

"use client";
import { useRef, useState } from "react";
import { Todo } from "../types/todo";

export default function AddTodoForm({
  source,
  onCreated,
}: {
  source: string;
  onCreated: (todo: Todo) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const addButtonRef = useRef<HTMLButtonElement>(null);

  const hasError = Boolean(errorMessage);

  const openForm = () => {
    setIsOpen(true);
    setDescription("");
    setErrorMessage(null);
  };

  const closeForm = () => {
    setIsOpen(false);
    setDescription("");
    setErrorMessage(null);
    setIsSubmitting(false);
    addButtonRef.current?.focus();
  };

  const handleChange = (value: string) => {
    setDescription(value);
    if (errorMessage) setErrorMessage(null);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLFormElement>) => {
    if (event.key === "Escape" && !isSubmitting) {
      closeForm();
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = description.trim();
    if (!trimmed) {
      setErrorMessage("Todo description can't be empty.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await fetch("/api/todos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, todo: { description: trimmed } }),
      });

      if (!response.ok) {
        let message = "Couldn't add todo. Please try again.";
        try {
          const data = await response.json();
          if (data && typeof data.error === "string") {
            message = data.error;
          }
        } catch {
          // ignore parse failures, use fallback message
        }
        throw new Error(message);
      }

      const { todo: created } = await response.json();
      onCreated(created);
      closeForm();
    } catch (error) {
      console.error(error);
      setIsSubmitting(false);
      setErrorMessage(error instanceof Error ? error.message : "Couldn't add todo. Please try again.");
    }
  };

  if (!isOpen) {
    return (
      <button
        ref={addButtonRef}
        type="button"
        onClick={openForm}
        className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2 min-h-11 rounded-lg border border-gray-300 dark:border-gray-700 text-sm font-bold text-black dark:text-white bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 dark:focus-visible:ring-offset-black transition-colors duration-150"
      >
        <span aria-hidden="true">+</span> Add Todo
      </button>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      onKeyDown={handleKeyDown}
      className="flex shrink-0 w-full max-w-3xl flex-col items-stretch gap-2 py-3 px-4 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-zinc-900 sm:flex-row sm:items-center sm:gap-2"
    >
      <div className="flex-1 flex flex-col gap-1">
        <label htmlFor="add-todo-description" className="sr-only">
          What needs to be done?
        </label>
        <input
          id="add-todo-description"
          type="text"
          value={description}
          onChange={(event) => handleChange(event.target.value)}
          placeholder="What needs to be done?"
          autoFocus
          disabled={isSubmitting}
          aria-invalid={hasError}
          aria-describedby={hasError ? "add-todo-error" : undefined}
          className={`flex-1 min-h-10 px-4 py-1.5 rounded-md border text-sm text-black dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus-visible:ring-2 disabled:opacity-50 disabled:cursor-not-allowed bg-white dark:bg-black ${hasError ? "border-red-500 dark:border-red-500 focus-visible:ring-red-500" : "border-gray-300 dark:border-gray-700 focus-visible:ring-blue-500"}`}
        />
        {errorMessage && (
          <p id="add-todo-error" role="alert" className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1">
            <span aria-hidden="true">⚠</span> {errorMessage}
          </p>
        )}
      </div>
      <div className="flex gap-2 shrink-0">
        <button
          type="submit"
          disabled={isSubmitting}
          className="inline-flex items-center justify-center gap-2 min-h-10 px-4 py-1.5 rounded-md border border-transparent text-sm font-bold text-white bg-black dark:bg-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 dark:focus-visible:ring-offset-zinc-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150"
        >
          {isSubmitting ? (
            <>
              <span
                aria-hidden="true"
                className="h-4 w-4 rounded-full border-2 border-white/40 dark:border-black/40 border-t-white dark:border-t-black animate-spin"
              />
              Adding…
            </>
          ) : (
            "Add"
          )}
        </button>
        <button
          type="button"
          onClick={closeForm}
          disabled={isSubmitting}
          aria-label="Cancel"
          className="inline-flex items-center justify-center min-h-10 px-4 py-1.5 rounded-md border border-gray-300 dark:border-gray-700 text-sm font-bold text-black dark:text-white bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 dark:focus-visible:ring-offset-black disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

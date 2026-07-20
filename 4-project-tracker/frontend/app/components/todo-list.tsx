"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Todo, TodoStatus } from "../types/todo";
import TodoItem from "./todo-item";
import AddTodoForm from "./add-todo-form";

const POLL_INTERVAL_MS = 20000;

const STATUS_RANK: Record<string, number> = {
  [TodoStatus.InProgress]: 0,
  [TodoStatus.Pending]: 1,
  [TodoStatus.Completed]: 2,
  [TodoStatus.Cancelled]: 3,
};

function getCreatedTime(todo: Todo): number {
  const created = todo.created instanceof Date ? todo.created : new Date(todo.created);
  return created.getTime();
}

function isDone(todo: Todo): boolean {
  return todo.status === TodoStatus.Completed || todo.status === TodoStatus.Cancelled;
}

export default function TodoList({ source }: { source: string }) {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [showDone, setShowDone] = useState(false);
  const busyIdsRef = useRef<Set<string>>(new Set());
  // Ids of todos created locally that haven't yet been confirmed present in a
  // poll response. Protects against a poll racing the (eventually consistent)
  // Sheet write and silently dropping the new todo from the list.
  const pendingNewIdsRef = useRef<Set<string>>(new Set());

  const handleSavingChange = (id: string, isSaving: boolean) => {
    if (isSaving) {
      busyIdsRef.current.add(id);
    } else {
      busyIdsRef.current.delete(id);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const fetchTodos = async () => {
      try {
        const response = await fetch(`/api/todos?source=${encodeURIComponent(source)}`);
        if (!response.ok) {
          let message = "Couldn't load todos. Please try again.";
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
        const { todos } = await response.json();
        if (!cancelled) {
          setTodos(todos);
          setFetchError(null);
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
          setFetchError(error instanceof Error ? error.message : "Couldn't load todos. Please try again.");
        }
      }
    }
    fetchTodos();
    return () => {
      cancelled = true;
    };
  }, [source, retryCount]);

  // Poll the backing sheet periodically so edits made elsewhere (another tab,
  // device, or directly in the Sheet) show up without a manual refresh.
  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const poll = async () => {
      if (inFlight) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      inFlight = true;
      try {
        const response = await fetch(`/api/todos?source=${encodeURIComponent(source)}`);
        if (!response.ok) {
          throw new Error(`Poll failed with status ${response.status}`);
        }
        const { todos: fetched } = await response.json();
        if (cancelled) return;
        // Any pending-created id that's now present in the poll response is
        // confirmed written to the Sheet, so it no longer needs protecting.
        for (const t of fetched as Todo[]) {
          pendingNewIdsRef.current.delete(t.id);
        }
        setTodos((prev) => {
          const prevById = new Map(prev.map((t) => [t.id, t]));
          const merged: Todo[] = fetched.map((t: Todo) =>
            busyIdsRef.current.has(t.id) && prevById.has(t.id) ? (prevById.get(t.id) as Todo) : t
          );
          // Keep any locally-known todos that are busy (or newly created and not yet
          // confirmed) but weren't (yet) returned by the poll, to avoid dropping them.
          for (const t of prev) {
            if (
              (busyIdsRef.current.has(t.id) || pendingNewIdsRef.current.has(t.id)) &&
              !merged.some((m) => m.id === t.id)
            ) {
              merged.push(t);
            }
          }
          return merged;
        });
      } catch (error) {
        // Polling failures are silent — the retry banner is reserved for the initial load.
        console.error(error);
      } finally {
        inFlight = false;
      }
    };

    const intervalId = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [source]);

  // Animate reorders (e.g. completing a todo slides it to the bottom) using
  // the native View Transitions API. No-op fallback in browsers without it.
  const animatedSetTodos: typeof setTodos = (updater) => {
    if (typeof document !== "undefined" && "startViewTransition" in document) {
      (document as unknown as { startViewTransition: (cb: () => void) => void }).startViewTransition(() =>
        setTodos(updater)
      );
    } else {
      setTodos(updater);
    }
  };

  const handleCreated = (todo: Todo) => {
    pendingNewIdsRef.current.add(todo.id);
    setTodos((prev) => [...prev, todo]);
  };

  const handleRetry = () => {
    setRetryCount((count) => count + 1);
  };

  const sortedTodos = useMemo(() => {
    return [...todos].sort((a, b) => {
      const rankA = STATUS_RANK[a.status] ?? Number.MAX_SAFE_INTEGER;
      const rankB = STATUS_RANK[b.status] ?? Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      const priorityA = a.priority ?? Number.MAX_SAFE_INTEGER;
      const priorityB = b.priority ?? Number.MAX_SAFE_INTEGER;
      if (priorityA !== priorityB) return priorityA - priorityB;
      return getCreatedTime(a) - getCreatedTime(b);
    });
  }, [todos]);

  const visibleTodos = useMemo(
    () => (showDone ? sortedTodos : sortedTodos.filter((todo) => !isDone(todo))),
    [sortedTodos, showDone]
  );
  const doneCount = sortedTodos.length - sortedTodos.filter((todo) => !isDone(todo)).length;

    return (
        <div className="flex flex-col w-full flex-1 min-h-0 gap-3">
          <AddTodoForm source={source} onCreated={handleCreated} />
          {fetchError && (
            <div role="alert" className="flex items-center gap-2 text-sm text-red-400 shrink-0">
              <span aria-hidden="true">⚠</span>
              <span>{fetchError}</span>
              <button
                type="button"
                onClick={handleRetry}
                className="underline font-bold hover:no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-red-500"
              >
                Retry
              </button>
            </div>
          )}
          <ul className="flex flex-col gap-2 w-full flex-1 min-h-0 overflow-y-auto pr-1 pb-16">
            {visibleTodos.map((todo) => (
              <li key={todo.id} className="w-full todo-row" style={{ viewTransitionName: `todo-${todo.id}` }}>
                <TodoItem todo={todo} source={source} onChange={animatedSetTodos} onSavingChange={handleSavingChange} />
              </li>
            ))}
            {doneCount > 0 && (
              <li className="w-full flex justify-center pt-1">
                <button
                  type="button"
                  onClick={() => {
                    if (typeof document !== "undefined" && "startViewTransition" in document) {
                      (document as unknown as { startViewTransition: (cb: () => void) => void }).startViewTransition(
                        () => setShowDone((v) => !v)
                      );
                    } else {
                      setShowDone((v) => !v);
                    }
                  }}
                  className="text-xs font-medium text-gray-400 hover:text-white px-3 py-1.5 rounded-full border border-white/10 bg-white/5 backdrop-blur-sm hover:bg-white/10 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  {showDone ? "Hide done" : `See ${doneCount} done`}
                </button>
              </li>
            )}
          </ul>
        </div>
    );
    }

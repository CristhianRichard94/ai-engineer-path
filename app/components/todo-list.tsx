"use client";
import { useEffect, useMemo, useState } from "react";
import { Todo, TodoStatus } from "../types/todo";
import TodoItem from "./todo-item";
import AddTodoForm from "./add-todo-form";

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

export default function TodoList({ source }: { source: string }) {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

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

  const handleCreated = (todo: Todo) => {
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
      return getCreatedTime(a) - getCreatedTime(b);
    });
  }, [todos]);

    return (
        <div className="flex flex-col w-full flex-1 min-h-0 gap-3">
          <AddTodoForm source={source} onCreated={handleCreated} />
          {fetchError && (
            <div role="alert" className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 shrink-0">
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
            {sortedTodos.map((todo) => (
              <li key={todo.id} className="w-full">
                <TodoItem todo={todo} source={source} onChange={setTodos} />
              </li>
            ))}
          </ul>
        </div>
    );
    }

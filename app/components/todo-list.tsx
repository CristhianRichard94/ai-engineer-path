"use client";
import { useEffect, useState } from "react";
import { Todo } from "../types/todo";
import TodoItem from "./todo-item";
import AddTodoForm from "./add-todo-form";

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

    return (
        <>
          <AddTodoForm source={source} onCreated={handleCreated} />
          {fetchError && (
            <div role="alert" className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
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
          <ul>
            {[...todos].sort((a, b) => a.status.localeCompare(b.status)).map((todo) => (
              <li key={todo.id} className="text-black dark:text-white">
                <TodoItem todo={todo} />
              </li>
            ))}
          </ul>
        </>
    );
    }

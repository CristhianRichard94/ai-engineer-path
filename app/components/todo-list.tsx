"use client";
import { useEffect, useMemo, useState } from "react";
import { Todo, TodoStatus } from "../types/todo";
import TodoItem from "./todo-item";

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

  useEffect(() => {
    const fetchTodos = async () => {
      try {
        const response = await fetch(`/api/todos?source=${encodeURIComponent(source)}`);
        if (!response.ok) throw new Error("Failed to fetch todos");
        const { todos } = await response.json();
        setTodos(todos);
      } catch (error) {
        console.error(error);
      }
    }
    fetchTodos();
  }, [source]);

  const sortedTodos = useMemo(() => {
    return [...todos].sort((a, b) => {
      const rankA = STATUS_RANK[a.status] ?? Number.MAX_SAFE_INTEGER;
      const rankB = STATUS_RANK[b.status] ?? Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      return getCreatedTime(a) - getCreatedTime(b);
    });
  }, [todos]);

    return (
        <ul className="flex flex-col gap-2 w-full">
          {sortedTodos.map((todo) => (
            <li key={todo.id} className="w-full">
              <TodoItem todo={todo} source={source} onChange={setTodos} />
            </li>
          ))}
        </ul>
    );
    }

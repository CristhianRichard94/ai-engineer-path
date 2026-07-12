"use client";
import { useEffect, useState } from "react";
import { Todo } from "../types/todo";
import TodoItem from "./todo-item";

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

    return (
        <ul>
          {todos.sort((a, b) => a.status.localeCompare(b.status)).map((todo) => (
            <li key={todo.id} className="text-black dark:text-white">
              <TodoItem todo={todo} />
            </li>
          ))}
        </ul>
    );
    }
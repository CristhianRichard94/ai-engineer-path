import { Todo } from "../types/todo";
import { getDateString } from "../utils/date";

export default function TodoItem({ todo }: { todo: Todo }) {

    return (
            <div className={`flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-8 px-8 sm:items-start border border-gray-300 dark:border-gray-700 rounded-lg shadow-md todo ${todo.status}`}>
                <h5 className="text-lg font-bold text-black dark:text-white text-ellipsis overflow-hidden">{todo.description}</h5>
                <span className="text-xs text-gray-500 dark:text-gray-400 self-end">Created on {getDateString(todo.created)}</span>
                <span className="text-xs text-gray-500 dark:text-gray-400 self-end">{todo.status}</span>
                {todo.doneDate && (
                    <span className="text-xs text-gray-500 dark:text-gray-400 self-end">Completed on {getDateString(todo.doneDate)}</span>
                )}
            </div>
    );
}
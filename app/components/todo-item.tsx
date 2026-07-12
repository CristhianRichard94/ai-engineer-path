"use client";
import { useEffect, useRef, useState } from "react";
import { Todo, TodoStatus } from "../types/todo";
import { getISOString, getShortDateString } from "../utils/date";

const STATUS_OPTIONS = Object.values(TodoStatus);

const STATUS_CLASSES: Record<string, string> = {
    [TodoStatus.InProgress]:
        "text-amber-700 bg-amber-50 border-amber-300 dark:text-amber-300 dark:bg-amber-950/40 dark:border-amber-800",
    [TodoStatus.Pending]:
        "text-gray-700 bg-gray-100 border-gray-300 dark:text-gray-300 dark:bg-gray-800/60 dark:border-gray-600",
    [TodoStatus.Completed]:
        "text-green-700 bg-green-50 border-green-300 dark:text-green-300 dark:bg-green-950/40 dark:border-green-800",
    [TodoStatus.Cancelled]:
        "text-red-700 bg-red-50 border-red-300 dark:text-red-300 dark:bg-red-950/40 dark:border-red-800",
};

const BASE_SELECT_CLASSES =
    "text-xs font-medium rounded-md border px-2 py-1 h-7 min-w-[104px] appearance-none focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 dark:focus:ring-offset-zinc-900 disabled:opacity-60 disabled:cursor-wait cursor-pointer";

const SPINNER_CLASSES =
    "inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin text-gray-400 dark:text-gray-500 ml-1.5";

type TodoItemProps = {
    todo: Todo;
    source: string;
    onChange: (updater: (prev: Todo[]) => Todo[]) => void;
};

class AbortedPatchError extends Error {
    constructor() {
        super("Request aborted");
        this.name = "AbortedPatchError";
    }
}

async function patchTodo(source: string, id: string, updates: Record<string, unknown>, signal?: AbortSignal) {
    try {
        const response = await fetch("/api/todos", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source, id, updates }),
            signal,
        });
        if (!response.ok) {
            throw new Error("Failed to update todo");
        }
        return response.json();
    } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
            throw new AbortedPatchError();
        }
        throw error;
    }
}

export default function TodoItem({ todo, source, onChange }: TodoItemProps) {
    const [status, setStatus] = useState<TodoStatus>(todo.status);
    const [doneDate, setDoneDate] = useState<Date | string | undefined>(todo.doneDate);
    const [statusSaving, setStatusSaving] = useState(false);
    const [statusError, setStatusError] = useState<string | null>(null);
    const [showStatusSpinner, setShowStatusSpinner] = useState(false);
    const statusTokenRef = useRef(0);

    const [description, setDescription] = useState(todo.description);
    const [isEditingDescription, setIsEditingDescription] = useState(false);
    const [descriptionDraft, setDescriptionDraft] = useState(todo.description);
    const [descriptionSaving, setDescriptionSaving] = useState(false);
    const [descriptionError, setDescriptionError] = useState<string | null>(null);
    const [showDescriptionSpinner, setShowDescriptionSpinner] = useState(false);
    const [descriptionDraftError, setDescriptionDraftError] = useState<string | null>(null);
    const descriptionTokenRef = useRef(0);
    const descriptionInputRef = useRef<HTMLInputElement>(null);

    const statusAbortRef = useRef<AbortController | null>(null);
    const descriptionAbortRef = useRef<AbortController | null>(null);
    const statusSpinnerTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const descriptionSpinnerTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const resortTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        return () => {
            statusAbortRef.current?.abort();
            descriptionAbortRef.current?.abort();
            if (statusSpinnerTimeoutRef.current) clearTimeout(statusSpinnerTimeoutRef.current);
            if (descriptionSpinnerTimeoutRef.current) clearTimeout(descriptionSpinnerTimeoutRef.current);
            if (resortTimeoutRef.current) clearTimeout(resortTimeoutRef.current);
        };
    }, []);

    useEffect(() => {
        setStatus(todo.status);
        setDoneDate(todo.doneDate);
    }, [todo.status, todo.doneDate]);

    useEffect(() => {
        setDescription(todo.description);
        if (!isEditingDescription) {
            setDescriptionDraft(todo.description);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [todo.description]);

    useEffect(() => {
        if (isEditingDescription && descriptionInputRef.current) {
            descriptionInputRef.current.focus();
            descriptionInputRef.current.select();
        }
    }, [isEditingDescription]);

    const handleStatusChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
        const newStatus = event.target.value as TodoStatus;
        if (newStatus === status) return;

        const previousStatus = status;
        const previousDoneDate = doneDate;

        let newDoneDate: Date | string | undefined = doneDate;
        const updates: Record<string, unknown> = { status: newStatus };
        if (newStatus === TodoStatus.Completed) {
            newDoneDate = new Date();
            updates.doneDate = getISOString(newDoneDate);
        } else if (previousStatus === TodoStatus.Completed) {
            newDoneDate = undefined;
            updates.doneDate = null;
        }

        setStatus(newStatus);
        setDoneDate(newDoneDate);
        setStatusError(null);
        setStatusSaving(true);

        statusAbortRef.current?.abort();
        const controller = new AbortController();
        statusAbortRef.current = controller;

        const token = ++statusTokenRef.current;
        if (statusSpinnerTimeoutRef.current) clearTimeout(statusSpinnerTimeoutRef.current);
        const spinnerTimeout = setTimeout(() => {
            if (statusTokenRef.current === token) setShowStatusSpinner(true);
        }, 300);
        statusSpinnerTimeoutRef.current = spinnerTimeout;

        try {
            await patchTodo(source, todo.id, updates, controller.signal);
            if (statusTokenRef.current !== token) return;
            clearTimeout(spinnerTimeout);
            setShowStatusSpinner(false);
            setStatusSaving(false);
            if (resortTimeoutRef.current) clearTimeout(resortTimeoutRef.current);
            resortTimeoutRef.current = setTimeout(() => {
                if (statusTokenRef.current !== token) return;
                onChange((prev) =>
                    prev.map((t) => (t.id === todo.id ? { ...t, status: newStatus, doneDate: newDoneDate } : t))
                );
            }, 600);
        } catch (error) {
            if (error instanceof AbortedPatchError) return;
            if (statusTokenRef.current !== token) return;
            clearTimeout(spinnerTimeout);
            console.error(error);
            setStatus(previousStatus);
            setDoneDate(previousDoneDate);
            setStatusError("Failed to update status.");
            setStatusSaving(false);
            setShowStatusSpinner(false);
        }
    };

    const startEditingDescription = () => {
        if (descriptionSaving) return;
        setDescriptionDraft(description);
        setDescriptionDraftError(null);
        setIsEditingDescription(true);
    };

    const commitDescription = async () => {
        const trimmed = descriptionDraft.trim();
        if (trimmed.length === 0) {
            setDescriptionDraft(description);
            setDescriptionDraftError(null);
            setIsEditingDescription(false);
            return;
        }
        if (trimmed === description) {
            setIsEditingDescription(false);
            return;
        }

        const previousDescription = description;
        setDescription(trimmed);
        setIsEditingDescription(false);
        setDescriptionError(null);
        setDescriptionSaving(true);

        descriptionAbortRef.current?.abort();
        const controller = new AbortController();
        descriptionAbortRef.current = controller;

        const token = ++descriptionTokenRef.current;
        if (descriptionSpinnerTimeoutRef.current) clearTimeout(descriptionSpinnerTimeoutRef.current);
        const spinnerTimeout = setTimeout(() => {
            if (descriptionTokenRef.current === token) setShowDescriptionSpinner(true);
        }, 300);
        descriptionSpinnerTimeoutRef.current = spinnerTimeout;

        try {
            await patchTodo(source, todo.id, { description: trimmed }, controller.signal);
            if (descriptionTokenRef.current !== token) return;
            clearTimeout(spinnerTimeout);
            setShowDescriptionSpinner(false);
            setDescriptionSaving(false);
            onChange((prev) => prev.map((t) => (t.id === todo.id ? { ...t, description: trimmed } : t)));
        } catch (error) {
            if (error instanceof AbortedPatchError) return;
            if (descriptionTokenRef.current !== token) return;
            clearTimeout(spinnerTimeout);
            console.error(error);
            setDescription(previousDescription);
            setDescriptionDraft(previousDescription);
            setDescriptionError("Failed to update description.");
            setDescriptionSaving(false);
            setShowDescriptionSpinner(false);
        }
    };

    const handleDescriptionKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            if (descriptionDraft.trim().length === 0) {
                setDescriptionDraftError("Description can't be empty.");
                return;
            }
            commitDescription();
        } else if (event.key === "Escape") {
            setDescriptionDraft(description);
            setDescriptionDraftError(null);
            setIsEditingDescription(false);
        }
    };

    const handleDescriptionTriggerKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (descriptionSaving) return;
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            startEditingDescription();
        }
    };

    const createdISO = getISOString(todo.created);
    const createdShort = getShortDateString(todo.created);
    const doneDateShort = doneDate ? getShortDateString(doneDate) : null;

    return (
        <div className={`todo ${status} group flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 w-full max-w-3xl px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-zinc-900 hover:border-gray-400 dark:hover:border-gray-600 transition-colors`}>
            {isEditingDescription ? (
                <input
                    ref={descriptionInputRef}
                    type="text"
                    autoFocus
                    value={descriptionDraft}
                    onChange={(event) => {
                        setDescriptionDraft(event.target.value);
                        if (descriptionDraftError) setDescriptionDraftError(null);
                    }}
                    onBlur={commitDescription}
                    onKeyDown={handleDescriptionKeyDown}
                    className="text-sm font-medium text-black dark:text-white bg-white dark:bg-zinc-800 border border-blue-400 dark:border-blue-500 rounded px-1 -mx-1 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 min-w-0 w-full"
                />
            ) : (
                <div
                    role="button"
                    tabIndex={0}
                    aria-disabled={descriptionSaving}
                    onClick={startEditingDescription}
                    onKeyDown={handleDescriptionTriggerKeyDown}
                    className={`text-sm font-medium text-black dark:text-white truncate rounded px-1 -mx-1 hover:bg-gray-100 dark:hover:bg-white/5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 dark:focus:ring-offset-zinc-900 flex-1 min-w-0 ${descriptionSaving ? "cursor-wait" : "cursor-text"}`}
                >
                    {description}
                    {showDescriptionSpinner && <span className={SPINNER_CLASSES} aria-hidden />}
                </div>
            )}

            <div className="flex flex-row items-center justify-between gap-2 w-full sm:w-auto sm:contents">
                <div className="flex flex-col shrink-0">
                    <select
                        value={status}
                        disabled={statusSaving}
                        onChange={handleStatusChange}
                        className={`${BASE_SELECT_CLASSES} ${statusError ? "border-red-500 dark:border-red-500" : STATUS_CLASSES[status]}`}
                    >
                        {STATUS_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                                {option}
                            </option>
                        ))}
                    </select>
                    {showStatusSpinner && <span className={SPINNER_CLASSES} aria-hidden />}
                </div>

                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 shrink-0 whitespace-nowrap">
                    <span title={createdISO}>{createdShort}</span>
                    {doneDateShort && (
                        <>
                            <span className="text-gray-300 dark:text-gray-600" aria-hidden>
                                ·
                            </span>
                            <span title={getISOString(doneDate as Date | string)}>{doneDateShort}</span>
                        </>
                    )}
                </div>
            </div>

            {statusError && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5" role="alert">
                    {statusError}
                </p>
            )}
            {descriptionDraftError && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5" role="alert">
                    {descriptionDraftError}
                </p>
            )}
            {descriptionError && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5" role="alert">
                    {descriptionError}
                </p>
            )}
        </div>
    );
}

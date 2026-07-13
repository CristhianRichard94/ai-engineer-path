"use client";
import { useEffect, useRef, useState } from "react";
import { Todo, TodoStatus } from "../types/todo";
import { getISOString, getShortDateString } from "../utils/date";

const STATUS_OPTIONS = Object.values(TodoStatus);

const PRIORITY_OPTIONS = ["", "1", "2", "3", "4", "5"];

const PRIORITY_CLASSES: Record<string, string> = {
    "1": "text-red-700 bg-red-50 border-red-300 dark:text-red-300 dark:bg-red-900/50 dark:border-red-600/70",
    "2": "text-orange-700 bg-orange-50 border-orange-300 dark:text-orange-300 dark:bg-orange-900/50 dark:border-orange-600/70",
    "3": "text-amber-700 bg-amber-50 border-amber-300 dark:text-amber-300 dark:bg-amber-900/50 dark:border-amber-600/70",
    "4": "text-blue-700 bg-blue-50 border-blue-300 dark:text-blue-300 dark:bg-blue-900/50 dark:border-blue-600/70",
    "5": "text-gray-700 bg-gray-100 border-gray-300 dark:text-gray-300 dark:bg-gray-700/70 dark:border-gray-500",
    "": "text-gray-400 bg-transparent border-gray-300 border-dashed dark:text-gray-500 dark:border-gray-600",
};

const STATUS_CLASSES: Record<string, string> = {
    [TodoStatus.InProgress]:
        "text-amber-700 bg-amber-50 border-amber-300 dark:text-amber-300 dark:bg-amber-900/50 dark:border-amber-600/70",
    [TodoStatus.Pending]:
        "text-gray-700 bg-gray-100 border-gray-300 dark:text-gray-300 dark:bg-gray-700/70 dark:border-gray-500",
    [TodoStatus.Completed]:
        "text-green-700 bg-green-50 border-green-300 dark:text-green-300 dark:bg-green-900/50 dark:border-green-600/70",
    [TodoStatus.Cancelled]:
        "text-red-700 bg-red-50 border-red-300 dark:text-red-300 dark:bg-red-900/50 dark:border-red-600/70",
};

const STATUS_CARD_BG: Record<string, string> = {
    [TodoStatus.InProgress]: "bg-amber-50/60 dark:bg-amber-950/30",
    [TodoStatus.Pending]:    "bg-white dark:bg-zinc-900",
    [TodoStatus.Completed]:  "bg-green-50/60 dark:bg-green-950/30",
    [TodoStatus.Cancelled]:  "bg-red-50/60 dark:bg-red-950/30",
};

const BASE_SELECT_CLASSES =
    "text-xs font-medium rounded-md border pl-2 pr-6 py-1 h-7 min-w-[104px] appearance-none focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 dark:focus:ring-offset-zinc-900 disabled:opacity-60 disabled:cursor-wait cursor-pointer hover:brightness-95 dark:hover:brightness-110 transition-[filter]";

const SPINNER_CLASSES =
    "inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin text-gray-400 dark:text-gray-500 ml-1.5";

type TodoItemProps = {
    todo: Todo;
    source: string;
    onChange: (updater: (prev: Todo[]) => Todo[]) => void;
    onSavingChange?: (id: string, isSaving: boolean) => void;
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

export default function TodoItem({ todo, source, onChange, onSavingChange }: TodoItemProps) {
    const [status, setStatus] = useState<TodoStatus>(todo.status);
    const [doneDate, setDoneDate] = useState<Date | string | undefined>(todo.doneDate);
    const [statusSaving, setStatusSaving] = useState(false);
    const [resortPending, setResortPending] = useState(false);
    const [statusError, setStatusError] = useState<string | null>(null);
    const [showStatusSpinner, setShowStatusSpinner] = useState(false);
    const statusTokenRef = useRef(0);

    const [priority, setPriority] = useState<string>(todo.priority ? String(todo.priority) : "");
    const [prioritySaving, setPrioritySaving] = useState(false);
    const [priorityResortPending, setPriorityResortPending] = useState(false);
    const [priorityError, setPriorityError] = useState<string | null>(null);
    const [showPrioritySpinner, setShowPrioritySpinner] = useState(false);
    const priorityTokenRef = useRef(0);

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
    const priorityAbortRef = useRef<AbortController | null>(null);
    const statusSpinnerTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const descriptionSpinnerTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const prioritySpinnerTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const resortTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const priorityResortTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        return () => {
            statusAbortRef.current?.abort();
            descriptionAbortRef.current?.abort();
            priorityAbortRef.current?.abort();
            if (statusSpinnerTimeoutRef.current) clearTimeout(statusSpinnerTimeoutRef.current);
            if (descriptionSpinnerTimeoutRef.current) clearTimeout(descriptionSpinnerTimeoutRef.current);
            if (prioritySpinnerTimeoutRef.current) clearTimeout(prioritySpinnerTimeoutRef.current);
            if (resortTimeoutRef.current) clearTimeout(resortTimeoutRef.current);
            if (priorityResortTimeoutRef.current) clearTimeout(priorityResortTimeoutRef.current);
            onSavingChange?.(todo.id, false);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Report combined "busy" state (status saving, pending resort, description saving,
    // or priority saving/resort) to the parent so poll merges can avoid clobbering
    // local optimistic state.
    useEffect(() => {
        onSavingChange?.(
            todo.id,
            statusSaving || resortPending || descriptionSaving || prioritySaving || priorityResortPending
        );
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [statusSaving, resortPending, descriptionSaving, prioritySaving, priorityResortPending, todo.id]);

    useEffect(() => {
        setStatus(todo.status);
        setDoneDate(todo.doneDate);
    }, [todo.status, todo.doneDate]);

    useEffect(() => {
        setPriority(todo.priority ? String(todo.priority) : "");
    }, [todo.priority]);

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

        // Register the busy flag synchronously, before any async work starts,
        // so a poll can never land in the gap between the optimistic update
        // and the effect-based registration (which runs after render commit).
        onSavingChange?.(todo.id, true);

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
            setResortPending(true);
            resortTimeoutRef.current = setTimeout(() => {
                if (statusTokenRef.current !== token) {
                    setResortPending(false);
                    return;
                }
                onChange((prev) =>
                    prev.map((t) => (t.id === todo.id ? { ...t, status: newStatus, doneDate: newDoneDate } : t))
                );
                setResortPending(false);
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

    const handlePriorityChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
        const newPriority = event.target.value;
        if (newPriority === priority) return;

        const previousPriority = priority;
        const updates: Record<string, unknown> = { priority: newPriority ? parseInt(newPriority, 10) : null };

        // Register the busy flag synchronously, before any async work starts,
        // so a poll can never land in the gap between the optimistic update
        // and the effect-based registration (which runs after render commit).
        onSavingChange?.(todo.id, true);

        setPriority(newPriority);
        setPriorityError(null);
        setPrioritySaving(true);

        priorityAbortRef.current?.abort();
        const controller = new AbortController();
        priorityAbortRef.current = controller;

        const token = ++priorityTokenRef.current;
        if (prioritySpinnerTimeoutRef.current) clearTimeout(prioritySpinnerTimeoutRef.current);
        const spinnerTimeout = setTimeout(() => {
            if (priorityTokenRef.current === token) setShowPrioritySpinner(true);
        }, 300);
        prioritySpinnerTimeoutRef.current = spinnerTimeout;

        try {
            await patchTodo(source, todo.id, updates, controller.signal);
            if (priorityTokenRef.current !== token) return;
            clearTimeout(spinnerTimeout);
            setShowPrioritySpinner(false);
            setPrioritySaving(false);
            if (priorityResortTimeoutRef.current) clearTimeout(priorityResortTimeoutRef.current);
            setPriorityResortPending(true);
            priorityResortTimeoutRef.current = setTimeout(() => {
                if (priorityTokenRef.current !== token) {
                    setPriorityResortPending(false);
                    return;
                }
                onChange((prev) =>
                    prev.map((t) =>
                        t.id === todo.id
                            ? { ...t, priority: newPriority ? parseInt(newPriority, 10) : undefined }
                            : t
                    )
                );
                setPriorityResortPending(false);
            }, 600);
        } catch (error) {
            if (error instanceof AbortedPatchError) return;
            if (priorityTokenRef.current !== token) return;
            clearTimeout(spinnerTimeout);
            console.error(error);
            setPriority(previousPriority);
            setPriorityError("Failed to update priority.");
            setPrioritySaving(false);
            setShowPrioritySpinner(false);
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

        // Register the busy flag synchronously, before any async work starts,
        // so a poll can never land in the gap between the optimistic update
        // and the effect-based registration (which runs after render commit).
        onSavingChange?.(todo.id, true);

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
        <div className={`todo ${status} group flex flex-col gap-1.5 w-full max-w-3xl px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md ${STATUS_CARD_BG[status]} hover:border-gray-400 dark:hover:border-gray-600 transition-colors`}>
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

            <div className="flex flex-row items-center justify-between gap-2 w-full">
                <div className="flex flex-col shrink-0">
                    <div className="relative inline-block">
                        <select
                            value={priority}
                            disabled={prioritySaving}
                            onChange={handlePriorityChange}
                            aria-label="Priority"
                            className={`${BASE_SELECT_CLASSES} !min-w-[64px] ${priorityError ? "border-red-500 dark:border-red-500" : (PRIORITY_CLASSES[priority] ?? PRIORITY_CLASSES[""])}`}
                        >
                            {PRIORITY_OPTIONS.map((option) => (
                                <option
                                    key={option || "unset"}
                                    value={option}
                                    className="bg-[#1f2937] text-white"
                                >
                                    {option ? `P${option}` : "–"}
                                </option>
                            ))}
                        </select>
                        <svg
                            aria-hidden="true"
                            viewBox="0 0 20 20"
                            fill="none"
                            className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-current opacity-70"
                        >
                            <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </div>
                    {showPrioritySpinner && <span className={SPINNER_CLASSES} aria-hidden />}
                </div>

                <div className="flex flex-col shrink-0">
                    <div className="relative inline-block">
                        <select
                            value={status}
                            disabled={statusSaving}
                            onChange={handleStatusChange}
                            className={`${BASE_SELECT_CLASSES} ${statusError ? "border-red-500 dark:border-red-500" : STATUS_CLASSES[status]}`}
                        >
                            {STATUS_OPTIONS.map((option) => (
                                <option
                                    key={option}
                                    value={option}
                                    className="bg-[#1f2937] text-white"
                                >
                                    {option}
                                </option>
                            ))}
                        </select>
                        <svg
                            aria-hidden="true"
                            viewBox="0 0 20 20"
                            fill="none"
                            className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-current opacity-70"
                        >
                            <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </div>
                    {showStatusSpinner && <span className={SPINNER_CLASSES} aria-hidden />}
                </div>

                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 shrink-0 whitespace-nowrap">
                    <span
                        title={`Source: ${todo.source}`}
                        className="px-1.5 py-0.5 rounded border border-gray-300 dark:border-gray-600 text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 truncate max-w-[80px]"
                    >
                        {todo.source}
                    </span>
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

            {priorityError && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5" role="alert">
                    {priorityError}
                </p>
            )}
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

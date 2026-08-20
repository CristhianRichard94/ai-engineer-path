"use client";
import { useEffect, useState } from "react";
import { extractSpreadsheetId, type AllowedSpreadsheet } from "@/app/utils/spreadsheet-id";

const STORAGE_KEY = "todo_source";

type SheetPickerProps = {
    source: string;
    onSourceChange: (source: string) => void;
};

export default function SheetPicker({ source, onSourceChange }: SheetPickerProps) {
    const [options, setOptions] = useState<AllowedSpreadsheet[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);

    // Only allow-listed spreadsheets are usable (see ALLOWED_SPREADSHEET_IDS
    // on the server), so the picker is a dropdown populated from the server
    // instead of a free-text field — the client can never submit an
    // arbitrary string that reaches the backend as `source`.
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const response = await fetch("/api/todos/sources");
                if (!response.ok) {
                    throw new Error("Couldn't load the sheet list.");
                }
                const { sources } = await response.json();
                if (!cancelled) {
                    setOptions(Array.isArray(sources) ? sources : []);
                    setLoadError(null);
                }
            } catch (error) {
                if (!cancelled) {
                    setLoadError(error instanceof Error ? error.message : "Couldn't load the sheet list.");
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    const activeId = extractSpreadsheetId(source) ?? source;

    // If the current source (e.g. the built-in default, or a stale
    // localStorage value) isn't in the allow-list, fall back to the first
    // allowed option so the app doesn't keep querying an ID the backend will
    // reject with 403.
    useEffect(() => {
        if (loading || loadError || options.length === 0) return;
        if (!options.some((option) => option.id === activeId)) {
            try {
                localStorage.setItem(STORAGE_KEY, options[0].id);
            } catch {
                // localStorage may be unavailable — still update in-memory state.
            }
            onSourceChange(options[0].id);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loading, loadError, options, activeId]);

    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const nextId = event.target.value;
        if (!nextId) return;
        try {
            localStorage.setItem(STORAGE_KEY, nextId);
        } catch {
            // localStorage may be unavailable (e.g. private browsing with storage
            // disabled) — still update in-memory state for this session.
        }
        onSourceChange(nextId);
    };

    if (loading) {
        return (
            <p className="text-xs text-gray-400" role="status">
                Loading sheets…
            </p>
        );
    }

    if (loadError) {
        return (
            <p role="alert" className="text-xs text-red-400">
                {loadError}
            </p>
        );
    }

    if (options.length === 0) {
        return (
            <p className="text-xs text-gray-400">
                No sheets configured. Set ALLOWED_SPREADSHEET_IDS on the server.
            </p>
        );
    }

    return (
        <div className="flex flex-col items-center gap-1 text-xs">
            <label htmlFor="sheet-picker" className="sr-only">
                Active sheet
            </label>
            <select
                id="sheet-picker"
                value={options.some((option) => option.id === activeId) ? activeId : options[0].id}
                onChange={handleChange}
                title={activeId}
                className="text-xs bg-white/5 border border-white/10 rounded px-2 py-1 text-gray-300 hover:text-white max-w-[240px] focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
                {options.map((option) => (
                    <option key={option.id} value={option.id} className="bg-slate-900 text-white">
                        {option.label}
                    </option>
                ))}
            </select>
        </div>
    );
}

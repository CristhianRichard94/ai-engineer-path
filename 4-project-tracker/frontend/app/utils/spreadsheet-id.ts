/**
 * Extracts a Google Sheets spreadsheet ID from either a full spreadsheet URL
 * or a raw ID string. Has no server-only dependencies so it's safe to import
 * from client components (e.g. the sheet picker) as well as the server-side
 * sheets service.
 *
 * Returns `null` if the resolved value doesn't look like a plausible Google
 * Sheets ID, instead of passing an unvalidated raw string through to callers
 * (some of which build Sheets API URLs from it).
 */

const SPREADSHEET_ID_PATTERN = /^[a-zA-Z0-9-_]{20,}$/;

export function extractSpreadsheetId(source: string): string | null {
    if (!source) return null;
    const match = source.match(/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    const candidate = match ? match[1] : source.trim();
    return SPREADSHEET_ID_PATTERN.test(candidate) ? candidate : null;
}

export type AllowedSpreadsheet = { id: string; label: string };

/**
 * Parses the server-side `ALLOWED_SPREADSHEET_IDS` env var: a comma-separated
 * list of `id` or `id:Label` entries, e.g.
 * `abc123...:Work,def456...:Personal`. Label is optional and defaults to the
 * ID itself.
 *
 * This is a single-user personal tool, so a server-side allow-list stands in
 * for full auth/OAuth scoping per spreadsheet — only IDs listed here may be
 * read or written via the API routes.
 */
export function getAllowedSpreadsheets(): AllowedSpreadsheet[] {
    const raw = process.env.ALLOWED_SPREADSHEET_IDS || "";
    return raw
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean)
        .map((entry) => {
            const [id, label] = entry.split(":");
            return { id: (id || "").trim(), label: (label || id || "").trim() };
        })
        .filter((entry) => SPREADSHEET_ID_PATTERN.test(entry.id));
}

export function isAllowedSpreadsheetId(id: string): boolean {
    return getAllowedSpreadsheets().some((entry) => entry.id === id);
}

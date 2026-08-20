import { createSign } from "crypto";
import { Todo, TodoStatus } from "@/app/types/todo";
import { extractSpreadsheetId } from "@/app/utils/spreadsheet-id";

// Each todo status now lives in its own sheet tab. Tab is the source of truth
// for a todo's status — the stored status column value (if any) is ignored on
// read and always overwritten on write.
const STATUS_TABS: Record<TodoStatus, string> = {
    [TodoStatus.Pending]: "Todo",
    [TodoStatus.InProgress]: "In Progress",
    [TodoStatus.Completed]: "Done",
    [TodoStatus.Cancelled]: "Cancelled",
};

const ALL_STATUSES = Object.keys(STATUS_TABS) as TodoStatus[];

type TokenCache = { token: string; expiresAt: number };

export { extractSpreadsheetId };

class SheetsService {
    private tokenCache: TokenCache | null = null;
    // Cache of which tabs have been confirmed to exist per spreadsheet, to
    // avoid re-fetching metadata / re-issuing addSheet requests on every call.
    private ensuredTabsCache: Map<string, Set<string>> = new Map();

    extractSpreadsheetId(source: string): string {
        return this.resolveSpreadsheetId(source);
    }

    /** Extracts and validates a spreadsheet ID, throwing if it doesn't look
     * like a plausible Google Sheets ID (defense in depth — callers such as
     * the API route are expected to have already validated against the
     * allow-list before reaching the service). */
    private resolveSpreadsheetId(source: string): string {
        const id = extractSpreadsheetId(source);
        if (!id) {
            throw new Error("Invalid spreadsheet id");
        }
        return id;
    }

    private async sleep(ms: number): Promise<void> {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    private async getAccessToken(): Promise<string> {
        if (this.tokenCache && this.tokenCache.expiresAt > Date.now()) {
            return this.tokenCache.token;
        }

        const email = process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL;
        const privateKey = process.env.GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY?.replace(/\\n/g, "\n");
        if (!email || !privateKey) {
            throw new Error("Missing GOOGLE_SERVICE_ACCOUNT_EMAIL / GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY");
        }

        const now = Math.floor(Date.now() / 1000);
        const header = { alg: "RS256", typ: "JWT" };
        const claims = {
            iss: email,
            scope: "https://www.googleapis.com/auth/spreadsheets",
            aud: "https://oauth2.googleapis.com/token",
            iat: now,
            exp: now + 3600,
        };
        const base64url = (obj: object) => Buffer.from(JSON.stringify(obj)).toString("base64url");

        const unsigned = `${base64url(header)}.${base64url(claims)}`;
        const signature = createSign("RSA-SHA256").update(unsigned).sign(privateKey, "base64url");
        const jwt = `${unsigned}.${signature}`;

        const response = await fetch("https://oauth2.googleapis.com/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
                grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
                assertion: jwt,
            }),
        });

        if (!response.ok) {
            throw new Error(`Failed to get access token: ${await response.text()}`);
        }

        const data = await response.json();
        this.tokenCache = { token: data.access_token, expiresAt: now * 1000 + (data.expires_in - 60) * 1000 };
        return data.access_token;
    }

    private async request(spreadsheetId: string, path: string, init: RequestInit = {}): Promise<any> {
        const token = await this.getAccessToken();
        const url = `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}${path}`;
        const response = await fetch(url, {
            ...init,
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
                ...init.headers,
            },
        });
        if (!response.ok) {
            throw new Error(`Sheets API error: ${await response.text()}`);
        }
        return response.json();
    }

    private rowToTodo(row: string[], status: TodoStatus): Todo {
        const [id, description, , source, created, doneDate, priority] = row;
        const createdDate = new Date(created);
        const parsedPriority = priority ? parseInt(priority, 10) : NaN;
        const validPriority =
            !isNaN(parsedPriority) && Number.isInteger(parsedPriority) && parsedPriority >= 1 && parsedPriority <= 5
                ? parsedPriority
                : undefined;
        return {
            id,
            description,
            source: source || "unknown",
            status,
            doneDate: doneDate ? new Date(doneDate) : undefined,
            created: isNaN(createdDate.getTime()) ? new Date(0) : createdDate,
            priority: validPriority,
        };
    }

    private toISOString(value: Date | string): string {
        return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
    }

    private sanitizeForSheet(value: string): string {
        if (/^[=+\-@\t\r]/.test(value)) {
            return `'${value}`;
        }
        return value;
    }

    private todoToRow(todo: Todo): string[] {
        return [
            this.sanitizeForSheet(todo.id),
            this.sanitizeForSheet(todo.description),
            this.sanitizeForSheet(todo.status),
            this.sanitizeForSheet(todo.source),
            this.sanitizeForSheet(this.toISOString(todo.created)),
            todo.doneDate ? this.sanitizeForSheet(this.toISOString(todo.doneDate)) : "",
            todo.priority !== undefined && todo.priority !== null ? String(todo.priority) : "",
        ];
    }

    /** Returns spreadsheet sheet metadata (title + sheetId) for every tab. */
    private async getSheetsMetadata(spreadsheetId: string): Promise<{ title: string; sheetId: number }[]> {
        const data = await this.request(spreadsheetId, `?fields=sheets.properties`);
        return (data.sheets || []).map((s: any) => ({
            title: s.properties.title as string,
            sheetId: s.properties.sheetId as number,
        }));
    }

    /** Writes the header row for `title` only if it doesn't already have one
     * (empty A1 cell). Covers both brand-new tabs and tabs that were created
     * on a previous call but interrupted before their header write. */
    private async ensureHeaderRow(spreadsheetId: string, title: string): Promise<void> {
        const data = await this.request(spreadsheetId, `/values/${encodeURIComponent(title)}!A1:G1`);
        const row: string[] = (data.values && data.values[0]) || [];
        if (row.length > 0 && row[0]) {
            return;
        }
        await this.request(spreadsheetId, `/values/${encodeURIComponent(title)}!A1:G1?valueInputOption=RAW`, {
            method: "PUT",
            body: JSON.stringify({
                values: [["id", "description", "status", "source", "created", "done_date", "priority"]],
            }),
        });
    }

    /** Ensures all 4 status tabs exist in the spreadsheet, creating any that are missing. */
    private async ensureStatusTabs(spreadsheetId: string): Promise<void> {
        const cached = this.ensuredTabsCache.get(spreadsheetId);
        const requiredTitles = Object.values(STATUS_TABS);
        if (cached && requiredTitles.every((t) => cached.has(t))) {
            return;
        }

        const existing = await this.getSheetsMetadata(spreadsheetId);
        const existingTitles = new Set(existing.map((s) => s.title));
        const missing = requiredTitles.filter((t) => !existingTitles.has(t));

        if (missing.length > 0) {
            try {
                await this.request(spreadsheetId, ":batchUpdate", {
                    method: "POST",
                    body: JSON.stringify({
                        requests: missing.map((title) => ({
                            addSheet: { properties: { title } },
                        })),
                    }),
                });
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                // Another concurrent request may have created the same tab(s)
                // first (first-use race). Treat "already exists" as success —
                // the header backfill below will re-check actual state —
                // instead of failing the whole call.
                if (!/already exists/i.test(message)) {
                    throw error;
                }
            }
        }

        // Backfill header rows for every required tab, not just the ones just
        // created — covers tabs that exist but were interrupted before their
        // header write completed on a previous call.
        await Promise.all(requiredTitles.map((title) => this.ensureHeaderRow(spreadsheetId, title)));

        this.ensuredTabsCache.set(spreadsheetId, new Set(requiredTitles));
    }

    private async getSheetId(spreadsheetId: string, tab: string): Promise<number> {
        const sheets = await this.getSheetsMetadata(spreadsheetId);
        const sheet = sheets.find((s) => s.title === tab);
        if (!sheet) {
            throw new Error(`Sheet ${tab} not found`);
        }
        return sheet.sheetId;
    }

    private async findRowNumberInTab(spreadsheetId: string, tab: string, id: string): Promise<number | null> {
        const data = await this.request(spreadsheetId, `/values/${encodeURIComponent(tab)}!A2:A`);
        const rows: string[][] = data.values || [];
        const index = rows.findIndex((row) => row[0] === id);
        return index === -1 ? null : index + 2; // header row + 1-based sheet rows
    }

    /** Deletes the row currently holding `expectedId` in `tab`, starting from
     * `rowNumber` as a hint. Before EACH delete attempt (not just once before
     * the retry loop), re-confirms via a fresh read that `rowNumber` still
     * holds `expectedId` — a row number captured earlier (or by a previous
     * attempt in this same loop) may no longer be correct if another write
     * raced it, or if a prior attempt's delete actually succeeded server-side
     * despite the client not getting a clean response. If the id has moved,
     * re-searches the tab for its current row and retries against that. If
     * the id isn't found anywhere in the tab, a previous attempt must have
     * already deleted it — treated as success rather than deleting whatever
     * unrelated row has since shifted into the stale position. The delete
     * itself is retried a few times with backoff on transient failures; if
     * all retries fail with no resolution, throws a clear error instead of
     * silently swallowing it (the caller may have already appended this row
     * to another tab, so a failed delete here can leave a duplicate). */
    private async deleteRowSafely(
        spreadsheetId: string,
        tab: string,
        rowNumber: number,
        expectedId: string
    ): Promise<void> {
        let targetRow = rowNumber;
        const sheetId = await this.getSheetId(spreadsheetId, tab);
        const MAX_ATTEMPTS = 3;
        let lastError: unknown;
        for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            const cellData = await this.request(
                spreadsheetId,
                `/values/${encodeURIComponent(tab)}!A${targetRow}:A${targetRow}`
            );
            const actualId = (cellData.values && cellData.values[0] && cellData.values[0][0]) || null;
            if (actualId !== expectedId) {
                const relocated = await this.findRowNumberInTab(spreadsheetId, tab, expectedId);
                if (relocated === null) {
                    // Id no longer exists anywhere in this tab — a previous
                    // attempt's deleteDimension call must have actually
                    // succeeded server-side even though we didn't observe a
                    // clean response. Treat as already deleted.
                    return;
                }
                targetRow = relocated;
            }

            try {
                await this.request(spreadsheetId, ":batchUpdate", {
                    method: "POST",
                    body: JSON.stringify({
                        requests: [
                            {
                                deleteDimension: {
                                    range: {
                                        sheetId,
                                        dimension: "ROWS",
                                        startIndex: targetRow - 1,
                                        endIndex: targetRow,
                                    },
                                },
                            },
                        ],
                    }),
                });
                return;
            } catch (error) {
                lastError = error;
                if (attempt < MAX_ATTEMPTS) {
                    await this.sleep(200 * attempt);
                }
            }
        }
        throw new Error(
            `Failed to delete row for todo ${expectedId} from tab "${tab}" after ${MAX_ATTEMPTS} attempts — ` +
                `the todo may now be duplicated across tabs and needs manual cleanup. Original error: ${
                    lastError instanceof Error ? lastError.message : String(lastError)
                }`
        );
    }

    /** Finds which tab (status) currently holds the row for `id`, and its row number. */
    private async findRow(
        spreadsheetId: string,
        id: string
    ): Promise<{ status: TodoStatus; tab: string; rowNumber: number } | null> {
        for (const status of ALL_STATUSES) {
            const tab = STATUS_TABS[status];
            const rowNumber = await this.findRowNumberInTab(spreadsheetId, tab, id);
            if (rowNumber !== null) {
                return { status, tab, rowNumber };
            }
        }
        return null;
    }

    async getTodos(source: string): Promise<Todo[]> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        await this.ensureStatusTabs(spreadsheetId);

        const results = await Promise.all(
            ALL_STATUSES.map(async (status) => {
                const tab = STATUS_TABS[status];
                const data = await this.request(spreadsheetId, `/values/${encodeURIComponent(tab)}!A2:G`);
                const rows: string[][] = data.values || [];
                return rows.filter((row) => row[0]).map((row) => this.rowToTodo(row, status));
            })
        );

        // If the same id ended up in more than one tab (a leftover duplicate
        // from a past partial move/failure), dedupe by id so the UI never
        // renders duplicate keys. ALL_STATUSES is already in tab priority
        // order (Todo > In Progress > Done > Cancelled), so keeping the first
        // occurrence keeps the highest-priority tab's copy.
        const seen = new Map<string, Todo>();
        for (const todo of results.flat()) {
            if (seen.has(todo.id)) {
                console.warn(
                    `Duplicate todo id "${todo.id}" found across status tabs; keeping the first occurrence and ignoring the rest.`
                );
                continue;
            }
            seen.set(todo.id, todo);
        }
        return Array.from(seen.values());
    }

    async addTodo(source: string, todo: Omit<Todo, "created"> & { created?: Date }): Promise<Todo> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        await this.ensureStatusTabs(spreadsheetId);

        const status = todo.status || TodoStatus.Pending;
        const tab = STATUS_TABS[status];
        const newTodo: Todo = { ...todo, status, created: todo.created || new Date() };
        await this.request(spreadsheetId, `/values/${encodeURIComponent(tab)}!A:G:append?valueInputOption=RAW`, {
            method: "POST",
            body: JSON.stringify({ values: [this.todoToRow(newTodo)] }),
        });
        return newTodo;
    }

    async updateTodo(
        source: string,
        id: string,
        updates: Partial<Omit<Todo, "id">> & { doneDate?: Date | string | null; priority?: number | null },
        currentStatusHint?: TodoStatus
    ): Promise<Todo> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        await this.ensureStatusTabs(spreadsheetId);

        // Locate the row. If the caller knows the current status, skip the
        // cross-tab search.
        let located: { status: TodoStatus; tab: string; rowNumber: number } | null = null;
        if (currentStatusHint) {
            const tab = STATUS_TABS[currentStatusHint];
            const rowNumber = await this.findRowNumberInTab(spreadsheetId, tab, id);
            if (rowNumber !== null) {
                located = { status: currentStatusHint, tab, rowNumber };
            }
        }
        if (!located) {
            located = await this.findRow(spreadsheetId, id);
        }
        if (!located) {
            throw new Error(`Todo ${id} not found`);
        }

        const isStatusChange =
            Object.prototype.hasOwnProperty.call(updates, "status") &&
            updates.status !== undefined &&
            updates.status !== located.status;

        if (isStatusChange) {
            const targetStatus = updates.status as TodoStatus;
            const targetTab = STATUS_TABS[targetStatus];

            // Read the full current row so we can carry over untouched fields.
            const rowData = await this.request(
                spreadsheetId,
                `/values/${encodeURIComponent(located.tab)}!A${located.rowNumber}:G${located.rowNumber}`
            );
            const row: string[] = (rowData.values && rowData.values[0]) || [];
            const current = this.rowToTodo(row, located.status);

            const merged: Todo = {
                ...current,
                ...updates,
                id,
                status: targetStatus,
                doneDate:
                    updates.doneDate === null
                        ? undefined
                        : updates.doneDate !== undefined
                        ? updates.doneDate
                        : current.doneDate,
                priority:
                    updates.priority === null
                        ? undefined
                        : updates.priority !== undefined
                        ? updates.priority
                        : current.priority,
            };

            // Append to target tab, then delete from the source tab.
            await this.request(
                spreadsheetId,
                `/values/${encodeURIComponent(targetTab)}!A:G:append?valueInputOption=RAW`,
                {
                    method: "POST",
                    body: JSON.stringify({ values: [this.todoToRow(merged)] }),
                }
            );

            await this.deleteRowSafely(spreadsheetId, located.tab, located.rowNumber, id);

            return merged;
        }

        // In-place update: no status change (or status not part of this update).
        const columnMap: Record<string, string> = Object.assign(Object.create(null), {
            description: "B",
            status: "C",
            source: "D",
            doneDate: "F",
            priority: "G",
        });

        const data: { range: string; values: string[][] }[] = [];

        for (const key of Object.keys(updates) as (keyof typeof updates)[]) {
            const column = columnMap[key as string];
            if (!column) continue; // id/created are never updated

            let cellValue: string;
            if (key === "doneDate") {
                const value = updates.doneDate;
                cellValue = value ? this.sanitizeForSheet(this.toISOString(value)) : "";
            } else if (key === "priority") {
                const value = updates.priority;
                cellValue = value !== null && value !== undefined ? String(value) : "";
            } else {
                const value = updates[key] as string | undefined;
                cellValue = value !== undefined ? this.sanitizeForSheet(value) : "";
            }

            data.push({ range: `${located.tab}!${column}${located.rowNumber}`, values: [[cellValue]] });
        }

        if (data.length > 0) {
            await this.request(spreadsheetId, `/values:batchUpdate`, {
                method: "POST",
                body: JSON.stringify({ valueInputOption: "RAW", data }),
            });
        }

        // Build the return value from a fresh read of just this row, since we no
        // longer hold a full-row snapshot (and never overwrite untouched columns).
        const rowData = await this.request(
            spreadsheetId,
            `/values/${encodeURIComponent(located.tab)}!A${located.rowNumber}:G${located.rowNumber}`
        );
        const row: string[] = (rowData.values && rowData.values[0]) || [];
        return this.rowToTodo(row, located.status);
    }

    async deleteTodo(source: string, id: string): Promise<void> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        await this.ensureStatusTabs(spreadsheetId);

        const located = await this.findRow(spreadsheetId, id);
        if (!located) {
            throw new Error(`Todo ${id} not found`);
        }

        await this.deleteRowSafely(spreadsheetId, located.tab, located.rowNumber, id);
    }
}

const sheetsService = new SheetsService();
export default sheetsService;
export { STATUS_TABS };

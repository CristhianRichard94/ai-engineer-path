import { createSign } from "crypto";
import { Todo, TodoStatus } from "@/app/types/todo";

const SHEET_NAME = process.env.GOOGLE_SHEETS_SHEET_NAME || "Sheet1";

type TokenCache = { token: string; expiresAt: number };

class SheetsService {
    private tokenCache: TokenCache | null = null;

    private extractSpreadsheetId(source: string): string {
        const match = source.match(/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
        return match ? match[1] : source;
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
        const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}${path}`;
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

    private rowToTodo(row: string[]): Todo {
        const [id, description, status, source, created, doneDate] = row;
        const createdDate = new Date(created);
        return {
            id,
            description,
            source: source || "unknown",
            status: ((status === "pending" ? "todo" : status) || "todo") as TodoStatus,
            doneDate: doneDate ? new Date(doneDate) : undefined,
            created: isNaN(createdDate.getTime()) ? new Date(0) : createdDate,
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
        ];
    }

    private async findRowNumber(spreadsheetId: string, id: string): Promise<number> {
        const data = await this.request(spreadsheetId, `/values/${SHEET_NAME}!A2:A`);
        const rows: string[][] = data.values || [];
        const index = rows.findIndex((row) => row[0] === id);
        if (index === -1) {
            throw new Error(`Todo ${id} not found`);
        }
        return index + 2; // header row + 1-based sheet rows
    }

    private async getSheetId(spreadsheetId: string): Promise<number> {
        const data = await this.request(spreadsheetId, `?fields=sheets.properties`);
        const sheet = data.sheets.find((s: any) => s.properties.title === SHEET_NAME);
        if (!sheet) {
            throw new Error(`Sheet ${SHEET_NAME} not found`);
        }
        return sheet.properties.sheetId;
    }

    async getTodos(source: string): Promise<Todo[]> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        const data = await this.request(spreadsheetId, `/values/${SHEET_NAME}!A2:F`);
        const rows: string[][] = data.values || [];
        return rows.filter((row) => row[0]).map((row) => this.rowToTodo(row));
    }

    async addTodo(source: string, todo: Omit<Todo, "created"> & { created?: Date }): Promise<Todo> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        const newTodo: Todo = { ...todo, created: todo.created || new Date() };
        await this.request(spreadsheetId, `/values/${SHEET_NAME}!A:F:append?valueInputOption=RAW`, {
            method: "POST",
            body: JSON.stringify({ values: [this.todoToRow(newTodo)] }),
        });
        return newTodo;
    }

    async updateTodo(
        source: string,
        id: string,
        updates: Partial<Omit<Todo, "id">> & { doneDate?: Date | string | null }
    ): Promise<Todo> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        const todos = await this.getTodos(source);
        const existing = todos.find((todo) => todo.id === id);
        if (!existing) {
            throw new Error(`Todo ${id} not found`);
        }
        const updated: Todo = {
            ...existing,
            ...updates,
            doneDate: updates.doneDate === null ? undefined : (updates.doneDate ?? existing.doneDate),
        };
        const rowNumber = await this.findRowNumber(spreadsheetId, id);
        await this.request(spreadsheetId, `/values/${SHEET_NAME}!A${rowNumber}:F${rowNumber}?valueInputOption=RAW`, {
            method: "PUT",
            body: JSON.stringify({ values: [this.todoToRow(updated)] }),
        });
        return updated;
    }

    async deleteTodo(source: string, id: string): Promise<void> {
        const spreadsheetId = this.extractSpreadsheetId(source);
        const rowNumber = await this.findRowNumber(spreadsheetId, id);
        const sheetId = await this.getSheetId(spreadsheetId);
        await this.request(spreadsheetId, ":batchUpdate", {
            method: "POST",
            body: JSON.stringify({
                requests: [
                    {
                        deleteDimension: {
                            range: { sheetId, dimension: "ROWS", startIndex: rowNumber - 1, endIndex: rowNumber },
                        },
                    },
                ],
            }),
        });
    }
}

const sheetsService = new SheetsService();
export default sheetsService;

// TODO: this endpoint (GET/POST/PATCH/DELETE) has no per-user auth/ownership
// checks — it relies on the shared-passcode session cookie (see
// middleware.ts) plus the ALLOWED_SPREADSHEET_IDS allow-list below.
import sheetsService from "@/app/services/sheets-service";
import { Todo, TodoStatus } from "@/app/types/todo";
import { extractSpreadsheetId, isAllowedSpreadsheetId } from "@/app/utils/spreadsheet-id";
import { NextRequest, NextResponse } from "next/server";

const MAX_DESCRIPTION_LENGTH = 500;

/**
 * Validates `source` resolves to a well-formed spreadsheet ID that's present
 * in the server-side ALLOWED_SPREADSHEET_IDS allow-list. This is a
 * single-user personal tool, so this allow-list stands in for full
 * auth/OAuth scoping per spreadsheet — it stops the app from being pointed
 * at (and writing to) arbitrary spreadsheets the service account happens to
 * have access to.
 */
function checkSpreadsheetAllowed(source: string): NextResponse | null {
    const id = extractSpreadsheetId(source);
    if (!id) {
        return NextResponse.json({ error: "Invalid spreadsheet id" }, { status: 400 });
    }
    if (!isAllowedSpreadsheetId(id)) {
        return NextResponse.json({ error: "Spreadsheet is not on the allow-list" }, { status: 403 });
    }
    return null;
}

export async function GET(request: NextRequest) {
    const source = request.nextUrl.searchParams.get("source");
    if (!source) {
        return NextResponse.json({ error: "Missing source" }, { status: 400 });
    }
    const rejection = checkSpreadsheetAllowed(source);
    if (rejection) return rejection;

    const todos = await sheetsService.getTodos(source);
    return NextResponse.json({ todos });
}

export async function POST(request: NextRequest) {
    const { source, todo } = await request.json();
    if (!source || !todo) {
        return NextResponse.json({ error: "Missing source or todo" }, { status: 400 });
    }
    if (typeof source !== "string") {
        return NextResponse.json({ error: "Invalid source" }, { status: 400 });
    }
    const rejection = checkSpreadsheetAllowed(source);
    if (rejection) return rejection;
    if (typeof todo.description !== "string" || todo.description.trim().length === 0) {
        return NextResponse.json({ error: "Description must be a non-empty string" }, { status: 400 });
    }
    if (todo.description.trim().length > MAX_DESCRIPTION_LENGTH) {
        return NextResponse.json({ error: `Description must be ${MAX_DESCRIPTION_LENGTH} characters or fewer` }, { status: 400 });
    }

    const now = new Date();
    const timestamp = now.toISOString().replace(/[-:T]/g, "").slice(0, 14);

    const newTodo: Omit<Todo, "created"> & { created?: Date } = {
        id: `id-${timestamp}`,
        description: todo.description.trim(),
        status: TodoStatus.Pending,
        source: "app",
        created: now,
    };

    const created = await sheetsService.addTodo(source, newTodo);
    return NextResponse.json({ todo: created });
}

export async function PATCH(request: NextRequest) {
    const { source, id, updates, currentStatus } = await request.json();
    if (!source || !id || !updates) {
        return NextResponse.json({ error: "Missing source, id or updates" }, { status: 400 });
    }
    if (typeof source !== "string") {
        return NextResponse.json({ error: "Invalid source" }, { status: 400 });
    }
    const rejection = checkSpreadsheetAllowed(source);
    if (rejection) return rejection;
    if (
        Object.prototype.hasOwnProperty.call(updates, "priority") &&
        updates.priority !== null &&
        updates.priority !== undefined &&
        (!Number.isInteger(updates.priority) || updates.priority < 1 || updates.priority > 5)
    ) {
        return NextResponse.json({ error: "Priority must be null or an integer between 1 and 5" }, { status: 400 });
    }
    // Optional hint: the status tab the todo currently lives in, so the
    // service can skip searching across all 4 tabs to locate the row.
    const updated = await sheetsService.updateTodo(source, id, updates, currentStatus as TodoStatus | undefined);
    return NextResponse.json({ todo: updated });
}

export async function DELETE(request: NextRequest) {
    const source = request.nextUrl.searchParams.get("source");
    const id = request.nextUrl.searchParams.get("id");
    if (!source || !id) {
        return NextResponse.json({ error: "Missing source or id" }, { status: 400 });
    }
    const rejection = checkSpreadsheetAllowed(source);
    if (rejection) return rejection;

    await sheetsService.deleteTodo(source, id);
    return NextResponse.json({ ok: true });
}

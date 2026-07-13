// TODO: this endpoint (GET/POST/PATCH/DELETE) has no auth/ownership checks — needs to be added.
import sheetsService from "@/app/services/sheets-service";
import { Todo, TodoStatus } from "@/app/types/todo";
import { NextRequest, NextResponse } from "next/server";

const MAX_DESCRIPTION_LENGTH = 500;

export async function GET(request: NextRequest) {
    const source = request.nextUrl.searchParams.get("source");
    if (!source) {
        return NextResponse.json({ error: "Missing source" }, { status: 400 });
    }
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
    const { source, id, updates } = await request.json();
    if (!source || !id || !updates) {
        return NextResponse.json({ error: "Missing source, id or updates" }, { status: 400 });
    }
    const updated = await sheetsService.updateTodo(source, id, updates);
    return NextResponse.json({ todo: updated });
}

export async function DELETE(request: NextRequest) {
    const source = request.nextUrl.searchParams.get("source");
    const id = request.nextUrl.searchParams.get("id");
    if (!source || !id) {
        return NextResponse.json({ error: "Missing source or id" }, { status: 400 });
    }
    await sheetsService.deleteTodo(source, id);
    return NextResponse.json({ ok: true });
}

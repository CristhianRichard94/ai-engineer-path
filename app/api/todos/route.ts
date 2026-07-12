import sheetsService from "@/app/services/sheets-service";
import { NextRequest, NextResponse } from "next/server";

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
    const created = await sheetsService.addTodo(source, todo);
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

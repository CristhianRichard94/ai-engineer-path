import { getAllowedSpreadsheets } from "@/app/utils/spreadsheet-id";
import { NextResponse } from "next/server";

// Returns the server-side allow-list of spreadsheets the sheet picker may
// offer, so the client never has to (and can't) submit an arbitrary
// spreadsheet ID/URL that reaches the backend as `source`.
export async function GET() {
    const sources = getAllowedSpreadsheets();
    return NextResponse.json({ sources });
}

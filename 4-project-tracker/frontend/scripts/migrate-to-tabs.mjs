#!/usr/bin/env node
// Migrates a single-tab todo spreadsheet (columns: id, description, status,
// source, created, done_date, priority) into the new 4-tab layout used by
// the frontend and MCP server: Todo / In Progress / Done / Cancelled.
//
// Usage:
//   node scripts/migrate-to-tabs.mjs <spreadsheetIdOrUrl> [--tab=Sheet1]
//
// Auth env vars (same as sheets-service.ts):
//   GOOGLE_SERVICE_ACCOUNT_EMAIL
//   GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY
//
// This script does NOT delete the old tab. Verify the migrated data, then
// delete it manually from Google Sheets once you're satisfied.

import { createSign } from "crypto";

const STATUS_TABS = {
  todo: "Todo",
  "in-progress": "In Progress",
  done: "Done",
  cancelled: "Cancelled",
};

const COLUMNS = ["id", "description", "status", "source", "created", "done_date", "priority"];
const FALLBACK_TAB_NAMES = ["Sheet1", "Todos"];

function extractSpreadsheetId(source) {
  const match = source.match(/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : source;
}

function parseArgs(argv) {
  const positional = [];
  let tab;
  for (const arg of argv) {
    if (arg.startsWith("--tab=")) {
      tab = arg.slice("--tab=".length);
    } else {
      positional.push(arg);
    }
  }
  return { spreadsheetSource: positional[0], tab };
}

async function getAccessToken() {
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
  const base64url = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");

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
  return data.access_token;
}

async function sheetsRequest(spreadsheetId, token, path, init = {}) {
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

function normalizeStatus(rawStatus) {
  const status = (rawStatus || "").trim();
  if (status === "pending") return "todo";
  if (STATUS_TABS[status]) return status;
  return "todo";
}

async function main() {
  const { spreadsheetSource, tab: explicitTab } = parseArgs(process.argv.slice(2));
  if (!spreadsheetSource) {
    console.error("Usage: node scripts/migrate-to-tabs.mjs <spreadsheetIdOrUrl> [--tab=Sheet1]");
    process.exit(1);
  }

  const spreadsheetId = extractSpreadsheetId(spreadsheetSource);
  const token = await getAccessToken();

  const meta = await sheetsRequest(spreadsheetId, token, "?fields=sheets.properties");
  const existingTitles = new Set((meta.sheets || []).map((s) => s.properties.title));

  let sourceTab = explicitTab;
  if (!sourceTab) {
    sourceTab = FALLBACK_TAB_NAMES.find((name) => existingTitles.has(name));
  }
  if (!sourceTab || !existingTitles.has(sourceTab)) {
    console.error(
      `Could not find a source tab to migrate from. Tried: ${
        explicitTab ? explicitTab : FALLBACK_TAB_NAMES.join(", ")
      }. Pass --tab=<name> to specify the tab explicitly.`
    );
    process.exit(1);
  }

  console.log(`Reading rows from "${sourceTab}"...`);
  const data = await sheetsRequest(spreadsheetId, token, `/values/${encodeURIComponent(sourceTab)}!A2:G`);
  const rows = (data.values || []).filter((row) => row[0]);
  console.log(`Found ${rows.length} row(s) to migrate.`);

  const requiredTitles = Object.values(STATUS_TABS);
  const missingTabs = requiredTitles.filter((t) => !existingTitles.has(t));
  if (missingTabs.length > 0) {
    console.log(`Creating missing tabs: ${missingTabs.join(", ")}`);
    await sheetsRequest(spreadsheetId, token, ":batchUpdate", {
      method: "POST",
      body: JSON.stringify({
        requests: missingTabs.map((title) => ({ addSheet: { properties: { title } } })),
      }),
    });
    await Promise.all(
      missingTabs.map((title) =>
        sheetsRequest(spreadsheetId, token, `/values/${encodeURIComponent(title)}!A1:G1?valueInputOption=RAW`, {
          method: "PUT",
          body: JSON.stringify({ values: [COLUMNS] }),
        })
      )
    );
  }

  const rowsByStatus = { todo: [], "in-progress": [], done: [], cancelled: [] };
  for (const row of rows) {
    // Pad short legacy rows first so indexing into column 2 (or any later
    // column) never creates a sparse array with holes, for both the status
    // lookup below and the row we eventually write out.
    const migratedRow = [...row];
    while (migratedRow.length < 7) migratedRow.push("");
    // Overwrite the stored status column so it's consistent with the tab
    // it's being placed into (tab is now the source of truth).
    const status = normalizeStatus(migratedRow[2]);
    migratedRow[2] = status;
    rowsByStatus[status].push(migratedRow);
  }

  for (const status of Object.keys(STATUS_TABS)) {
    const values = rowsByStatus[status];
    if (values.length === 0) continue;
    const tab = STATUS_TABS[status];
    await sheetsRequest(spreadsheetId, token, `/values/${encodeURIComponent(tab)}!A:G:append?valueInputOption=RAW`, {
      method: "POST",
      body: JSON.stringify({ values }),
    });
  }

  console.log("\nMigration summary:");
  for (const status of Object.keys(STATUS_TABS)) {
    console.log(`  ${STATUS_TABS[status]}: ${rowsByStatus[status].length} row(s)`);
  }

  console.log(
    `\nDone. The original "${sourceTab}" tab was NOT deleted. ` +
      `Verify the data in the new tabs (Todo / In Progress / Done / Cancelled), ` +
      `then delete "${sourceTab}" manually from Google Sheets once you're satisfied.`
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

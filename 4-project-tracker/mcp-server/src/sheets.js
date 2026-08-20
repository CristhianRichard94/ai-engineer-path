import { readFile } from "node:fs/promises";
import { GoogleAuth } from "google-auth-library";

const SHEET_ID =
  process.env.SHEET_ID || "1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U";
const SA_KEY_PATH = process.env.SA_KEY_PATH;

// Each todo status lives in its own sheet tab. Tab name is the source of
// truth for status — kept identical to the frontend's STATUS_TABS map so
// both clients operate on the same spreadsheet.
const STATUS_TABS = {
  todo: "Todo",
  "in-progress": "In Progress",
  done: "Done",
  cancelled: "Cancelled",
};
const ALL_STATUSES = Object.keys(STATUS_TABS);

const SCOPES = ["https://www.googleapis.com/auth/spreadsheets"];

let authClient = null;
async function getAuthClient() {
  if (authClient) return authClient;
  if (!SA_KEY_PATH) {
    throw new Error(
      "SA_KEY_PATH environment variable must be set to the path of the Google service account key file."
    );
  }
  const keyFile = JSON.parse(await readFile(SA_KEY_PATH, "utf-8"));
  const auth = new GoogleAuth({ credentials: keyFile, scopes: SCOPES });
  authClient = await auth.getClient();
  return authClient;
}

async function sheetsFetch(path, options = {}) {
  const client = await getAuthClient();
  const { token } = await client.getAccessToken();
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Sheets API error ${res.status}: ${body}`);
  }
  return res.json();
}

function todayDateString() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

const COLUMNS = [
  "id",
  "description",
  "status",
  "source",
  "created",
  "done_date",
  "priority",
];

/** Writes the header row for `title` only if it doesn't already have one
 * (empty A1 cell). Covers both brand-new tabs and tabs created on a previous
 * run but interrupted before their header write. */
async function ensureHeaderRow(title) {
  const data = await sheetsFetch(`/values/${encodeURIComponent(title)}!A1:G1`);
  const row = (data.values && data.values[0]) || [];
  if (row.length > 0 && row[0]) return;
  await sheetsFetch(
    `/values/${encodeURIComponent(title)}!A1:G1?valueInputOption=RAW`,
    {
      method: "PUT",
      body: JSON.stringify({ values: [COLUMNS] }),
    }
  );
}

/** Ensures all 4 status tabs exist, creating any that are missing (with a header row). */
let ensuredTabs = false;
async function ensureStatusTabs() {
  if (ensuredTabs) return;

  const meta = await sheetsFetch("?fields=sheets.properties");
  const existingTitles = new Set(
    (meta.sheets || []).map((s) => s.properties.title)
  );
  const requiredTitles = Object.values(STATUS_TABS);
  const missing = requiredTitles.filter((t) => !existingTitles.has(t));

  if (missing.length > 0) {
    try {
      await sheetsFetch(":batchUpdate", {
        method: "POST",
        body: JSON.stringify({
          requests: missing.map((title) => ({
            addSheet: { properties: { title } },
          })),
        }),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      // Another concurrent request (e.g. the frontend) may have created the
      // same tab(s) first on the shared spreadsheet's first use. Treat
      // "already exists" as success — the header backfill below re-checks
      // actual state — instead of failing the whole call.
      if (!/already exists/i.test(message)) {
        throw error;
      }
    }
  }

  // Backfill header rows for every required tab, not just the ones just
  // created — covers tabs that exist but were interrupted before their
  // header write completed on a previous run.
  await Promise.all(requiredTitles.map((title) => ensureHeaderRow(title)));

  ensuredTabs = true;
}

/** Read all data rows for a single tab (excludes header). Each row includes rowIndex (1-based sheet row) and status (tab-derived, overwriting any stored value). */
async function readRowsForStatus(status) {
  const tab = STATUS_TABS[status];
  const range = `${tab}!A2:G`;
  const data = await sheetsFetch(`/values/${encodeURIComponent(range)}`);
  const values = data.values || [];
  return values
    .map((row, i) => {
      const obj = { rowIndex: i + 2, tab };
      COLUMNS.forEach((col, idx) => {
        obj[col] = row[idx] ?? "";
      });
      obj.status = status; // tab is the source of truth, not the stored column
      return obj;
    })
    .filter((r) => r.id);
}

/** Read all data rows across all 4 status tabs, merged. If the same id
 * appears in more than one tab (a leftover duplicate from a past partial
 * move/failure), dedupe by id — keep the first occurrence in tab priority
 * order (ALL_STATUSES: Todo > In Progress > Done > Cancelled) and log a
 * warning, so callers never see/act on duplicate ids. */
async function readRows() {
  await ensureStatusTabs();
  const results = await Promise.all(ALL_STATUSES.map(readRowsForStatus));
  const seen = new Map();
  for (const row of results.flat()) {
    if (seen.has(row.id)) {
      console.warn(
        `Duplicate task id "${row.id}" found across status tabs; keeping the first occurrence and ignoring the rest.`
      );
      continue;
    }
    seen.set(row.id, row);
  }
  return [...seen.values()];
}

function generateId() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `id-${yyyy}${mm}${dd}${hh}${min}${ss}`;
}

function priorityForSort(r) {
  const p = Number(r.priority);
  return r.priority !== "" && !Number.isNaN(p) ? p : Infinity;
}

function sortByPriorityThenCreated(a, b) {
  const pDiff = priorityForSort(a) - priorityForSort(b);
  if (pDiff !== 0) return pDiff;
  return (a.created || "").localeCompare(b.created || "");
}

function groupByPriority(rows) {
  const groups = new Map();
  for (const r of rows) {
    const key = r.priority !== "" && r.priority != null ? Number(r.priority) : Infinity;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  return [...groups.entries()].sort((a, b) => a[0] - b[0]);
}

function formatSection(title, rows, counter) {
  if (rows.length === 0) return [];
  const lines = [`${title}:`];
  for (const [priority, rowsInGroup] of groupByPriority(rows)) {
    lines.push(`  P${priority === Infinity ? "?" : priority}:`);
    for (const r of rowsInGroup) {
      counter.n += 1;
      const createdDate = (r.created || "").slice(0, 10);
      lines.push(`    ${counter.n}. ${r.description} (created ${createdDate})`);
    }
  }
  return lines;
}

export async function listOpenTasks() {
  const rows = await readRows();
  const inProgress = rows.filter((r) => r.status === "in-progress").sort(sortByPriorityThenCreated);
  const ideas = rows.filter((r) => r.status === "todo").sort(sortByPriorityThenCreated);

  const counter = { n: 0 };
  const lines = [
    ...formatSection("In Progress", inProgress, counter),
    ...formatSection("Ideas", ideas, counter),
  ];
  const text = lines.length > 0 ? lines.join("\n") : "No open tasks.";

  const numbered = [];
  let i = 0;
  for (const r of [...inProgress, ...ideas]) {
    i += 1;
    numbered.push({ n: i, id: r.id, description: r.description });
  }

  return { text, numbered };
}

const VALID_SOURCES = ["pc", "terminal", "claude", "other"];

export async function addTask(description, source = "claude", priority) {
  if (!description || !description.trim()) {
    throw new Error("A non-empty task description is required.");
  }
  let p;
  if (priority !== undefined && priority !== null && priority !== "") {
    p = Number(priority);
    if (!Number.isInteger(p) || p < 1 || p > 5) {
      throw new Error("Priority must be an integer between 1 and 5.");
    }
  }
  await ensureStatusTabs();
  const src = VALID_SOURCES.includes(source) ? source : "other";
  const id = generateId();
  const priorityValue =
    priority !== undefined && priority !== null && priority !== ""
      ? String(p)
      : "";
  const values = [
    [id, description.trim(), "todo", src, todayDateString(), "", priorityValue],
  ];
  const tab = STATUS_TABS.todo;
  const range = `${tab}!A:G`;
  await sheetsFetch(
    `/values/${encodeURIComponent(range)}:append?valueInputOption=RAW`,
    { method: "POST", body: JSON.stringify({ values }) }
  );
  return { added: true, message: `Added task (id ${id}): ${description.trim()}` };
}

export async function editTask(query, description, priority) {
  if (!query || !query.trim()) {
    throw new Error("A non-empty task description or partial match is required.");
  }
  const hasDescription = description !== undefined && description !== null && description.trim();
  const hasPriority = priority !== undefined && priority !== null && priority !== "";
  if (!hasDescription && !hasPriority) {
    throw new Error("At least one of description or priority must be provided.");
  }
  let p;
  if (hasPriority) {
    p = Number(priority);
    if (!Number.isInteger(p) || p < 1 || p > 5) {
      throw new Error("Priority must be an integer between 1 and 5.");
    }
  }
  const needle = query.trim().toLowerCase();
  const rows = await readRows();
  const matches = rows.filter((r) => r.description.toLowerCase().includes(needle));

  if (matches.length === 0) {
    return { edited: false, message: `No matching task found for "${query}".` };
  }
  if (matches.length > 1) {
    const lines = matches.map((m) => `[id ${m.id}] ${m.description}`);
    return {
      edited: false,
      message: `Query "${query}" matched ${matches.length} tasks. Please use a more specific query:\n${lines.join(
        "\n"
      )}`,
      matches: lines,
    };
  }

  const match = matches[0];
  const data = [];
  if (hasDescription) {
    data.push({
      range: `${match.tab}!B${match.rowIndex}`,
      values: [[description.trim()]],
    });
  }
  if (hasPriority) {
    data.push({
      range: `${match.tab}!G${match.rowIndex}`,
      values: [[String(p)]],
    });
  }
  await sheetsFetch(`/values:batchUpdate`, {
    method: "POST",
    body: JSON.stringify({ valueInputOption: "RAW", data }),
  });

  const parts = [];
  if (hasDescription) {
    parts.push(`description "${match.description}" -> "${description.trim()}"`);
  }
  if (hasPriority) {
    parts.push(`priority -> ${p}`);
  }
  return {
    edited: true,
    message: `Edited task (id ${match.id}): ${parts.join(", ")}`,
  };
}

const sheetNumericIds = new Map();
async function getSheetNumericId(tab) {
  if (sheetNumericIds.has(tab)) return sheetNumericIds.get(tab);
  const meta = await sheetsFetch("?fields=sheets.properties");
  const sheet = (meta.sheets || []).find((s) => s.properties.title === tab);
  if (!sheet) throw new Error(`Sheet tab "${tab}" not found.`);
  sheetNumericIds.set(tab, sheet.properties.sheetId);
  return sheet.properties.sheetId;
}

async function deleteRow(tab, rowIndex) {
  const sheetId = await getSheetNumericId(tab);
  await sheetsFetch(`:batchUpdate`, {
    method: "POST",
    body: JSON.stringify({
      requests: [
        {
          deleteDimension: {
            range: {
              sheetId,
              dimension: "ROWS",
              startIndex: rowIndex - 1,
              endIndex: rowIndex,
            },
          },
        },
      ],
    }),
  });
}

/** Returns the current row number (1-based sheet row) for `id` in `tab`, or
 * null if not present. */
async function findRowNumberInTab(tab, id) {
  const data = await sheetsFetch(`/values/${encodeURIComponent(tab)}!A2:A`);
  const rows = data.values || [];
  const index = rows.findIndex((row) => row[0] === id);
  return index === -1 ? null : index + 2;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Deletes the row currently holding `expectedId` in `tab`, starting from
 * `rowIndex` as a hint. Before EACH delete attempt (not just once before the
 * retry loop), re-confirms via a fresh read that `rowIndex` still holds
 * `expectedId` — a row index captured earlier (or by a previous attempt in
 * this same loop) may no longer be correct if another write raced it, or if
 * a prior attempt's delete actually succeeded server-side despite not
 * getting a clean response. If the id has moved, re-searches the tab for its
 * current row and retries against that. If the id isn't found anywhere in
 * the tab, a previous attempt must have already deleted it — treated as
 * success rather than deleting whatever unrelated row has since shifted into
 * the stale position. The delete itself is retried a few times with backoff
 * on transient failures; if all retries fail with no resolution, throws a
 * clear error instead of silently swallowing it (the caller may have already
 * appended this row to another tab, so a failed delete here can leave a
 * duplicate). */
async function deleteRowSafely(tab, rowIndex, expectedId) {
  let targetRow = rowIndex;
  const MAX_ATTEMPTS = 3;
  let lastError;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const cellData = await sheetsFetch(
      `/values/${encodeURIComponent(tab)}!A${targetRow}:A${targetRow}`
    );
    const actualId =
      (cellData.values && cellData.values[0] && cellData.values[0][0]) || null;
    if (actualId !== expectedId) {
      const relocated = await findRowNumberInTab(tab, expectedId);
      if (relocated === null) {
        // Id no longer exists anywhere in this tab — a previous attempt's
        // deleteDimension call must have actually succeeded server-side even
        // though we didn't observe a clean response. Treat as already deleted.
        return;
      }
      targetRow = relocated;
    }

    try {
      await deleteRow(tab, targetRow);
      return;
    } catch (error) {
      lastError = error;
      if (attempt < MAX_ATTEMPTS) {
        await sleep(200 * attempt);
      }
    }
  }
  throw new Error(
    `Failed to delete row for task ${expectedId} from tab "${tab}" after ${MAX_ATTEMPTS} attempts — ` +
      `the task may now be duplicated across tabs and needs manual cleanup. Original error: ${
        lastError instanceof Error ? lastError.message : String(lastError)
      }`
  );
}

export async function deleteTask(query) {
  if (!query || !query.trim()) {
    throw new Error("A non-empty task description or partial match is required.");
  }
  const needle = query.trim().toLowerCase();
  const rows = await readRows();
  const matches = rows.filter((r) => r.description.toLowerCase().includes(needle));

  if (matches.length === 0) {
    return { deleted: false, message: `No matching task found for "${query}".` };
  }
  if (matches.length > 1) {
    const lines = matches.map((m) => `[id ${m.id}] ${m.description}`);
    return {
      deleted: false,
      message: `Query "${query}" matched ${matches.length} tasks. Please use a more specific query:\n${lines.join(
        "\n"
      )}`,
      matches: lines,
    };
  }

  const match = matches[0];
  await deleteRowSafely(match.tab, match.rowIndex, match.id);

  return {
    deleted: true,
    message: `Deleted task (id ${match.id}): ${match.description}`,
  };
}

export async function markTaskDone(query) {
  if (!query || !query.trim()) {
    throw new Error("A non-empty task description or partial match is required.");
  }
  const needle = query.trim().toLowerCase();
  const rows = await readRows();
  const matches = rows.filter(
    (r) => r.status !== "done" && r.description.toLowerCase().includes(needle)
  );

  if (matches.length === 0) {
    return {
      moved: false,
      message: `No matching open task found for "${query}".`,
    };
  }
  if (matches.length > 1) {
    const lines = matches.map((m) => `[id ${m.id}] ${m.description}`);
    return {
      moved: false,
      message: `Query "${query}" matched ${matches.length} tasks. Please use a more specific query:\n${lines.join(
        "\n"
      )}`,
      matches: lines,
    };
  }

  const match = matches[0];
  const doneTab = STATUS_TABS.done;

  // Move the row to the Done tab: append with status/done_date updated, then
  // delete the original row from its current tab.
  const values = [
    [
      match.id,
      match.description,
      "done",
      match.source,
      match.created,
      todayDateString(),
      match.priority,
    ],
  ];
  await sheetsFetch(
    `/values/${encodeURIComponent(doneTab)}!A:G:append?valueInputOption=RAW`,
    { method: "POST", body: JSON.stringify({ values }) }
  );
  await deleteRowSafely(match.tab, match.rowIndex, match.id);

  return {
    moved: true,
    message: `Marked done (id ${match.id}): ${match.description}`,
  };
}

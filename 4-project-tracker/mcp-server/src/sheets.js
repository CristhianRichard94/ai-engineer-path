import { readFile } from "node:fs/promises";
import { GoogleAuth } from "google-auth-library";

const SHEET_ID =
  process.env.SHEET_ID || "1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U";
const SHEET_TAB = process.env.SHEET_TAB || "Todos";
const SA_KEY_PATH = process.env.SA_KEY_PATH;

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

/** Read all data rows (excludes header). Each row: { rowIndex (1-based sheet row), id, description, status, source, created, done_date, priority } */
async function readRows() {
  const range = `${SHEET_TAB}!A2:G`;
  const data = await sheetsFetch(`/values/${encodeURIComponent(range)}`);
  const values = data.values || [];
  return values.map((row, i) => {
    const obj = { rowIndex: i + 2 };
    COLUMNS.forEach((col, idx) => {
      obj[col] = row[idx] ?? "";
    });
    return obj;
  });
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
  const src = VALID_SOURCES.includes(source) ? source : "other";
  const id = generateId();
  const priorityValue =
    priority !== undefined && priority !== null && priority !== ""
      ? String(p)
      : "";
  const values = [
    [id, description.trim(), "todo", src, todayDateString(), "", priorityValue],
  ];
  const range = `${SHEET_TAB}!A:G`;
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
      range: `${SHEET_TAB}!B${match.rowIndex}`,
      values: [[description.trim()]],
    });
  }
  if (hasPriority) {
    data.push({
      range: `${SHEET_TAB}!G${match.rowIndex}`,
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

let sheetNumericId = null;
async function getSheetNumericId() {
  if (sheetNumericId != null) return sheetNumericId;
  const meta = await sheetsFetch("");
  const sheet = (meta.sheets || []).find(
    (s) => s.properties.title === SHEET_TAB
  );
  if (!sheet) throw new Error(`Sheet tab "${SHEET_TAB}" not found.`);
  sheetNumericId = sheet.properties.sheetId;
  return sheetNumericId;
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
  const sheetId = await getSheetNumericId();
  await sheetsFetch(`:batchUpdate`, {
    method: "POST",
    body: JSON.stringify({
      requests: [
        {
          deleteDimension: {
            range: {
              sheetId,
              dimension: "ROWS",
              startIndex: match.rowIndex - 1,
              endIndex: match.rowIndex,
            },
          },
        },
      ],
    }),
  });

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
  await sheetsFetch(`/values:batchUpdate`, {
    method: "POST",
    body: JSON.stringify({
      valueInputOption: "RAW",
      data: [
        {
          range: `${SHEET_TAB}!C${match.rowIndex}`,
          values: [["done"]],
        },
        {
          range: `${SHEET_TAB}!F${match.rowIndex}`,
          values: [[todayDateString()]],
        },
      ],
    }),
  });

  return {
    moved: true,
    message: `Marked done (id ${match.id}): ${match.description}`,
  };
}

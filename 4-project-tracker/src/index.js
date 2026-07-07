#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { readFile, writeFile, stat } from "node:fs/promises";
import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");

const BACKLOG_PATH =
  process.env.BACKLOG_PATH || path.join(__dirname, "..", "BACKLOG.md");

const PROJECTS_ROOT = process.env.PROJECTS_ROOT || REPO_ROOT;

const SECTION_IDEAS = "## Ideas / candidates";
const SECTION_IN_PROGRESS = "## In Progress";
const SECTION_DONE = "## Done (recent)";

/**
 * Parse BACKLOG.md content into an ordered list of sections.
 * Each section: { header: string, headerLine: number, lines: string[] (raw lines incl. blanks, excluding header) }
 * `lines` spans from right after the header up to (but not including) the next "## " header or EOF.
 */
function parseSections(content) {
  const rawLines = content.split(/\r?\n/);
  const sections = [];
  let current = null;

  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i];
    if (line.startsWith("## ")) {
      current = { header: line, headerLine: i, lines: [] };
      sections.push(current);
    } else if (current) {
      current.lines.push(line);
    } else {
      // content before any "## " header (e.g. "# Backlog" title, intro text)
      if (!sections.preamble) sections.preamble = [];
      sections.preamble.push(line);
    }
  }

  return { sections, preamble: sections.preamble || [] };
}

/** Extract bullet task lines ("- ...") from a section's raw lines. */
function extractTasks(lines) {
  return lines
    .map((l) => l.trim())
    .filter((l) => l.startsWith("- ") && l.length > 2);
}

/** Rebuild full BACKLOG.md text from preamble + sections, preserving the given line ending style. */
function renderBacklog(preamble, sections, lineEnding = "\n") {
  const parts = [];
  parts.push(...preamble);
  for (const section of sections) {
    parts.push(section.header);
    parts.push(...section.lines);
  }
  // Trim trailing blank lines then ensure single trailing newline.
  while (parts.length && parts[parts.length - 1] === "") {
    parts.pop();
  }
  return parts.join(lineEnding) + lineEnding;
}

/** Detect the dominant line ending ("\r\n" or "\n") used in a file's content. */
function detectLineEnding(content) {
  return content.includes("\r\n") ? "\r\n" : "\n";
}

/** Strip a leading UTF-8 BOM character, if present. */
function stripBOM(content) {
  if (content.charCodeAt(0) === 0xfeff) {
    return content.slice(1);
  }
  return content;
}

/**
 * Reject values containing embedded newlines (CR or LF), which could be used
 * to inject fake "## Header" lines or otherwise corrupt BACKLOG.md structure.
 */
function assertNoNewlines(value, fieldName) {
  if (/[\r\n]/.test(value)) {
    throw new Error(
      `${fieldName} must not contain line breaks (found embedded \\r or \\n).`
    );
  }
}

/**
 * Simple in-process async mutex to serialize read-modify-write operations
 * against BACKLOG.md, preventing overlapping add_task/mark_task_done calls
 * from clobbering each other's writes.
 */
let backlogMutexTail = Promise.resolve();
function withBacklogLock(fn) {
  const run = backlogMutexTail.then(() => fn());
  // Swallow errors here so a rejected call doesn't permanently poison the
  // chain for subsequent callers; the original error still propagates to
  // the caller of `run` via the returned promise below.
  backlogMutexTail = run.catch(() => {});
  return run;
}

function todayDateString() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

async function readBacklog() {
  let content;
  try {
    content = await readFile(BACKLOG_PATH, "utf-8");
  } catch (err) {
    if (err.code === "ENOENT") {
      throw new Error(
        `BACKLOG.md not found at "${BACKLOG_PATH}". Create it at that path, or set the BACKLOG_PATH environment variable to point at your backlog file.`
      );
    }
    throw err;
  }
  return stripBOM(content);
}

async function writeBacklog(content) {
  await writeFile(BACKLOG_PATH, content, "utf-8");
}

async function listOpenTasks() {
  const content = await readBacklog();
  const { sections } = parseSections(content);

  const ideasSection = sections.find((s) => s.header === SECTION_IDEAS);
  const inProgressSection = sections.find(
    (s) => s.header === SECTION_IN_PROGRESS
  );

  const ideas = ideasSection ? extractTasks(ideasSection.lines) : [];
  const inProgress = inProgressSection
    ? extractTasks(inProgressSection.lines)
    : [];

  return { ideas, inProgress };
}

async function markTaskDone(query) {
  if (!query || !query.trim()) {
    throw new Error("A non-empty task description or partial match is required.");
  }
  assertNoNewlines(query, "query");

  return withBacklogLock(async () => {
    const content = await readBacklog();
    const lineEnding = detectLineEnding(content);
    const { sections, preamble } = parseSections(content);

    const ideasSection = sections.find((s) => s.header === SECTION_IDEAS);
    const inProgressSection = sections.find(
      (s) => s.header === SECTION_IN_PROGRESS
    );
    let doneSection = sections.find((s) => s.header === SECTION_DONE);

    const candidates = [
      { section: ideasSection, name: "Ideas / candidates" },
      { section: inProgressSection, name: "In Progress" },
    ];

    const needle = query.trim().toLowerCase();
    const allMatches = [];

    for (const { section, name } of candidates) {
      if (!section) continue;
      section.lines.forEach((line, idx) => {
        const trimmed = line.trim();
        if (trimmed.startsWith("- ") && trimmed.toLowerCase().includes(needle)) {
          allMatches.push({ idx, name, section, trimmed });
        }
      });
    }

    if (allMatches.length === 0) {
      return {
        moved: false,
        message: `No matching task found for "${query}" in "Ideas / candidates" or "In Progress".`,
      };
    }

    if (allMatches.length > 1) {
      const lines = allMatches.map((m) => `[${m.name}] ${m.trimmed}`);
      return {
        moved: false,
        message: `Query "${query}" matched ${allMatches.length} tasks. Please use a more specific query to disambiguate:\n${lines.join(
          "\n"
        )}`,
        matches: lines,
      };
    }

    const match = allMatches[0];
    const matchSection = match.section;

    const originalLine = matchSection.lines[match.idx];
    const trimmedLine = originalLine.trim();

    // Remove the matched line from its original section.
    matchSection.lines.splice(match.idx, 1);

    // Ensure a Done section exists; if not, create one at the end.
    if (!doneSection) {
      doneSection = { header: SECTION_DONE, headerLine: -1, lines: [] };
      sections.push(doneSection);
    }

    const doneEntry = `${trimmedLine} (${todayDateString()})`;

    // Insert after the header, keeping a leading blank line convention if present.
    const insertAt = doneSection.lines.length && doneSection.lines[0] === ""
      ? 1
      : 0;
    doneSection.lines.splice(insertAt, 0, doneEntry);

    const newContent = renderBacklog(preamble, sections, lineEnding);
    await writeBacklog(newContent);

    return {
      moved: true,
      message: `Moved task from "${match.name}" to "Done (recent)": ${doneEntry}`,
    };
  });
}

async function addTask(description) {
  if (!description || !description.trim()) {
    throw new Error("A non-empty task description is required.");
  }
  assertNoNewlines(description, "description");

  return withBacklogLock(async () => {
    const content = await readBacklog();
    const lineEnding = detectLineEnding(content);
    const { sections, preamble } = parseSections(content);

    let ideasSection = sections.find((s) => s.header === SECTION_IDEAS);
    if (!ideasSection) {
      ideasSection = { header: SECTION_IDEAS, headerLine: -1, lines: [] };
      sections.unshift(ideasSection);
    }

    const newLine = `- ${description.trim()}`;

    // Append before trailing blank lines at the end of the section, if any,
    // otherwise just push to the end.
    let insertAt = ideasSection.lines.length;
    while (insertAt > 0 && ideasSection.lines[insertAt - 1] === "") {
      insertAt--;
    }
    ideasSection.lines.splice(insertAt, 0, newLine);

    const newContent = renderBacklog(preamble, sections, lineEnding);
    await writeBacklog(newContent);

    return { added: true, message: `Added task to "Ideas / candidates": ${newLine}` };
  });
}

async function gitStatusSummary(projectFolder) {
  if (!projectFolder || !projectFolder.trim()) {
    throw new Error("A project folder name is required.");
  }

  // Guard against path traversal outside PROJECTS_ROOT.
  const sanitized = projectFolder.trim().replace(/^[/\\]+/, "");
  const targetDir = path.resolve(PROJECTS_ROOT, sanitized);
  const resolvedRoot = path.resolve(PROJECTS_ROOT);

  if (!targetDir.startsWith(resolvedRoot + path.sep) && targetDir !== resolvedRoot) {
    throw new Error(
      `Project folder must be a subfolder of ${PROJECTS_ROOT}.`
    );
  }

  let folderStat;
  try {
    folderStat = await stat(targetDir);
  } catch (err) {
    if (err.code === "ENOENT") {
      return {
        isGitRepo: false,
        clean: null,
        output: `Folder "${projectFolder}" was not found under ${PROJECTS_ROOT}.`,
      };
    }
    throw new Error(`Failed to access folder "${projectFolder}": ${err.message}`);
  }

  if (!folderStat.isDirectory()) {
    return {
      isGitRepo: false,
      clean: null,
      output: `"${projectFolder}" exists under ${PROJECTS_ROOT} but is not a directory.`,
    };
  }

  try {
    const { stdout } = await execFileAsync(
      "git",
      ["status", "--short"],
      { cwd: targetDir }
    );
    const trimmed = stdout.trim();
    return {
      isGitRepo: true,
      clean: trimmed.length === 0,
      output: trimmed.length === 0 ? "Working tree clean." : trimmed,
    };
  } catch (err) {
    const stderr = err.stderr ? String(err.stderr) : "";
    if (stderr.includes("not a git repository")) {
      return {
        isGitRepo: false,
        clean: null,
        output: `"${projectFolder}" is not a git repository.`,
      };
    }
    if (err.code === "ENOENT") {
      return {
        isGitRepo: false,
        clean: null,
        output: `Could not run git status in "${projectFolder}": git does not appear to be installed or is not on PATH.`,
      };
    }
    throw new Error(`Failed to run git status in "${projectFolder}": ${err.message}`);
  }
}

const server = new Server(
  { name: "project-tracker-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

const TOOLS = [
  {
    name: "list_open_tasks",
    description:
      'Parses the backlog file and returns open tasks under "## Ideas / candidates" and "## In Progress" (skips "## Done").',
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "mark_task_done",
    description:
      'Finds a task by exact text or partial match under "Ideas / candidates" or "In Progress", moves it to "## Done (recent)" with today\'s date appended, and removes it from its original section.',
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Full or partial text of the task to mark done.",
        },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "add_task",
    description: 'Appends a new task line to "## Ideas / candidates" in the backlog file.',
    inputSchema: {
      type: "object",
      properties: {
        description: {
          type: "string",
          description: "Description of the new task.",
        },
      },
      required: ["description"],
      additionalProperties: false,
    },
  },
  {
    name: "git_status_summary",
    description:
      "Runs `git status --short` in a subfolder of the projects root and returns the output, or a clear message if it is not a git repo.",
    inputSchema: {
      type: "object",
      properties: {
        projectFolder: {
          type: "string",
          description:
            "Name of the subfolder (of the projects root) to check, e.g. '1-ai-chat'.",
        },
      },
      required: ["projectFolder"],
      additionalProperties: false,
    },
  },
];

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;

  try {
    switch (name) {
      case "list_open_tasks": {
        const result = await listOpenTasks();
        return {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        };
      }
      case "mark_task_done": {
        const result = await markTaskDone(args.query);
        return {
          content: [{ type: "text", text: result.message }],
        };
      }
      case "add_task": {
        const result = await addTask(args.description);
        return {
          content: [{ type: "text", text: result.message }],
        };
      }
      case "git_status_summary": {
        const result = await gitStatusSummary(args.projectFolder);
        return {
          content: [{ type: "text", text: result.output }],
        };
      }
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (err) {
    return {
      isError: true,
      content: [{ type: "text", text: `Error: ${err.message}` }],
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Fatal error starting project-tracker-mcp server:", err);
  process.exit(1);
});

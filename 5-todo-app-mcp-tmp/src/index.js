#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { stat } from "node:fs/promises";
import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import * as sheets from "./sheets.js";

const execFileAsync = promisify(execFile);

const PROJECTS_ROOT =
  process.env.PROJECTS_ROOT || "C:\\Users\\Cristhian\\Documents\\projects";

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
      'Reads the "Todos" Google Sheet and returns open tasks (status "todo" or "in_progress"; skips "done").',
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "mark_task_done",
    description:
      'Finds an open task in the Todos sheet by exact text or partial match, sets its status to "done" and stamps done_date with today\'s date.',
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
    description: 'Appends a new row (status "todo") to the Todos Google Sheet.',
    inputSchema: {
      type: "object",
      properties: {
        description: {
          type: "string",
          description: "Description of the new task.",
        },
        source: {
          type: "string",
          enum: ["pc", "terminal", "claude", "other"],
          description: 'Where the task came from. Defaults to "claude".',
        },
        priority: {
          type: "integer",
          minimum: 1,
          maximum: 5,
          description: "Optional priority from 1 (highest) to 5 (lowest).",
        },
      },
      required: ["description"],
      additionalProperties: false,
    },
  },
  {
    name: "edit_task",
    description:
      "Finds an open or done task in the Todos sheet by exact text or partial match, and updates its description and/or priority. At least one of description or priority must be provided.",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Full or partial text of the task to find.",
        },
        description: {
          type: "string",
          description: "New description to replace the matched task's text with.",
        },
        priority: {
          type: "integer",
          minimum: 1,
          maximum: 5,
          description: "New priority from 1 (highest) to 5 (lowest).",
        },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "delete_task",
    description:
      "Finds a task in the Todos sheet by exact text or partial match and deletes its row entirely.",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Full or partial text of the task to delete.",
        },
      },
      required: ["query"],
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
            "Name of the subfolder (of the projects root) to check, e.g. 'ai-engineer-path'.",
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
        const result = await sheets.listOpenTasks();
        return {
          content: [{ type: "text", text: result.text }],
        };
      }
      case "mark_task_done": {
        const result = await sheets.markTaskDone(args.query);
        return {
          content: [{ type: "text", text: result.message }],
        };
      }
      case "add_task": {
        const result = await sheets.addTask(args.description, args.source, args.priority);
        return {
          content: [{ type: "text", text: result.message }],
        };
      }
      case "edit_task": {
        const result = await sheets.editTask(args.query, args.description, args.priority);
        return {
          content: [{ type: "text", text: result.message }],
        };
      }
      case "delete_task": {
        const result = await sheets.deleteTask(args.query);
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

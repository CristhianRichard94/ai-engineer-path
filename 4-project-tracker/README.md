# 4. Project Tracker (MCP server)

A local MCP (Model Context Protocol) server that reads/writes this repo's
`BACKLOG.md` and checks `git status` across sibling app folders in
`ai-engineer-path`. Built with the official
[`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk)
using the stdio transport.

## Tools exposed

- **`list_open_tasks`** — parses `BACKLOG.md` and returns items under
  `## Ideas / candidates` and `## In Progress` (skips `## Done`).
- **`mark_task_done`** — takes a task description or partial match string,
  moves the matching task into `## Done (recent)` with today's date appended.
- **`add_task`** — appends a new line to `## Ideas / candidates`.
- **`git_status_summary`** — given a subfolder name (e.g. `1-ai-chat`), runs
  `git status --short` there and returns the output.

## Setup

```bash
cd 4-project-tracker
npm install
```

### Environment variables (optional)

| Variable        | Default                          | Purpose                                 |
| --------------- | --------------------------------- | ---------------------------------------- |
| `BACKLOG_PATH`  | `<repo>/4-project-tracker/BACKLOG.md` | Path to the backlog file to read/write. |
| `PROJECTS_ROOT` | `<repo root>`                     | Root folder containing sibling app dirs. |

Defaults are computed relative to the script's own location, so no machine-specific
paths are needed. Override only if your setup differs.

### Run directly

```bash
npm start
```

Meant to be launched by an MCP client (Claude Code, Claude Desktop, etc.), not
run standalone for interactive use.

## Registered via `.mcp.json`

The repo root's `.mcp.json` already wires this server up with a relative path,
so it's auto-detected when Claude Code opens `ai-engineer-path`:

```json
{
  "mcpServers": {
    "project-tracker": {
      "type": "stdio",
      "command": "node",
      "args": ["4-project-tracker/src/index.js"]
    }
  }
}
```

Approve the trust prompt on first use.

## Notes

- `git_status_summary` refuses to operate outside `PROJECTS_ROOT` (blocks
  path traversal via `..` segments).
- If `BACKLOG.md` has no `## Done (recent)` section, `mark_task_done` creates one.
- If `BACKLOG.md` has no `## Ideas / candidates` section, `add_task` creates one.

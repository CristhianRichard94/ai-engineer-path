# project-tracker-mcp

A local MCP (Model Context Protocol) server that reads/writes a todos Google
Sheet (shared source of truth with a companion mobile todo app) and checks
`git status` across sibling project folders. Built with the official
[`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk)
using the stdio transport.

## Tools exposed

- **`list_open_tasks`** — reads the Todos sheet and returns rows with status
  `idea` or `in_progress` (skips `done`).
- **`mark_task_done`** — takes a task description or partial match string,
  sets that row's `status` to `done` and stamps `done_date` with today's date.
- **`add_task`** — appends a new row with status `idea` (`source` defaults to
  `"manual"`, or pass e.g. `"reel:<link>"`).
- **`git_status_summary`** — given a project folder name (a subfolder of the
  projects root), runs `git status --short` in that folder and returns the
  output, or a clear message if it's not a git repo.

## Sheet schema

Tab `Todos`, header row: `id | description | status | source | created | done_date`.
`status` is one of `idea`, `in_progress`, `done`.

## Setup

```bash
npm install
```

### Environment variables

| Variable        | Default                                                                  | Purpose                                        |
| --------------- | ------------------------------------------------------------------------- | ----------------------------------------------- |
| `SHEET_ID`      | `1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U`                           | Google Sheet ID (from its URL).                |
| `SHEET_TAB`     | `Todos`                                                                  | Tab name inside the sheet.                     |
| `SA_KEY_PATH`   | `C:\Users\Cristhian\Documents\projects\genai-406713-98a02f72ea99.json`  | Path to the service account JSON key.          |
| `PROJECTS_ROOT` | `C:\Users\Cristhian\Documents\projects`                                 | Root folder containing sibling projects.       |

The service account (`client_email` in the key file) must be shared as
**Editor** on the sheet. No extra IAM role or GCP project role needed beyond
that — just the Sheets API enabled on the key's project.

### Run directly

```bash
npm start
```

This starts the server on stdio — it's meant to be launched by an MCP client
(Claude Desktop, Claude Code, etc.), not run standalone in a terminal for
interactive use.

## Registering with Claude Code / Claude Desktop

Add this to your MCP config (e.g. `claude_desktop_config.json` or the
equivalent Claude Code MCP settings file):

```json
{
  "mcpServers": {
    "project-tracker": {
      "command": "node",
      "args": ["C:\\Users\\Cristhian\\Documents\\projects\\project-tracker-mcp\\src\\index.js"],
      "env": {
        "SHEET_ID": "1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U",
        "SHEET_TAB": "Todos",
        "SA_KEY_PATH": "C:\\Users\\Cristhian\\Documents\\projects\\genai-406713-98a02f72ea99.json",
        "PROJECTS_ROOT": "C:\\Users\\Cristhian\\Documents\\projects"
      }
    }
  }
}
```

Restart the client after adding the config so it picks up the new server.

## Notes

- `git_status_summary` refuses to operate outside `PROJECTS_ROOT` (blocks
  path traversal via `..` segments).
- `id` auto-increments from the max existing `id` in the sheet.
- The mobile React todo app should write to the same sheet/schema so this MCP
  and the app always see the same data — no separate sync step needed.

# Telegram → Sheet automation

A Make.com scenario forwards Telegram messages straight into the Todos Google
Sheet, tagged `source: telegram`, as an alternative capture path alongside
the mobile app and Claude Code's `add_task` MCP tool.

## Live setup (Make.com)

- Scenario: **TODO Bot Automation** (id `9515018`, team `2918420`), active.
- Modules: `telegram:WatchUpdates` → `google-sheets:addRow` (plus dedupe via
  a Make Data Store keyed on `chat.id`).
- Trigger: webhook named **"My Telegram Bot Updates webhook"** (hook id
  `4254530`, type `telegramapi`), bound to a Telegram bot via Make's
  Telegram connection (connection id `14423561`).
- Target sheet: same one `mcp-server` and the frontend use — see
  `frontend/README.md` / the sheet ID referenced there.
- Local copy of the scenario blueprint (exported, no secrets): see
  `frontend/todo-make-automation.blueprint.json`.

## Recreating it from scratch

1. In Make, create a Telegram connection: talk to
   [@BotFather](https://t.me/BotFather), create a bot, get its token, paste
   the token into Make's "Create a connection" dialog for the Telegram app.
   **The bot token lives only in Make's connection store — never commit it
   to this repo.**
2. Add a `Telegram > Watch Updates` trigger module, pick the connection from
   step 1.
3. Add a `Google Sheets > Add a Row` module targeting the Todos sheet,
   mapping the incoming message text to `description`, `status: idea`,
   `source: telegram`, `created: {{now}}`.
4. (Optional, matches current scenario) add a Data Store lookup on
   `chat.id` before the sheet write, to dedupe rapid double-sends.
5. Activate the scenario.

## Notes

- No bot token, webhook URL, or connection credentials are stored in this
  repo — all of that lives in Make.com's own secret store.
- If the scenario needs debugging, check it directly in Make.com (scenario
  id above) rather than re-deriving state from the blueprint file, which is
  a point-in-time export and may drift from the live scenario.

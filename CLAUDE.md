# AI Engineer Path — Project Instructions

## Team

- `ux-designer` — user flows, interaction states, information architecture.
- `ui-designer` — visual design and component specs, built on the UX flow.
- `software-engineer` — implements features/fixes/refactors.
- `qa-engineer` — reviews for bugs, edge cases, spec conformance, and ships/no-ship verdicts.

## Feature Development Workflow

Whenever the user requests a new feature or fix, do NOT stop after one implementation pass. Run this loop automatically, without asking for permission to continue.

**1. Design (conditional — user-facing features only)**
   - `ux-designer` defines the user flow: steps, decision points, and every non-happy-path state (loading, empty, error, edge cases).
   - `ui-designer` turns that flow into a visual/component spec (layout, states, responsive behavior, accessibility), consistent with the app's existing design system.
   - Skip both steps entirely for backend-only, API-only, or infra changes — go straight to implementation.

**2. Branch** — Before any code is written, create a worktree and feature branch:
   ```
   git worktree add .worktrees/<feature-name> -b feature/<feature-name>
   ```
   All implementation work happens inside that worktree. Never implement directly on `main`.

**3. Implement** — Delegate to `software-engineer`. Give it the full feature request, any relevant context (which app, existing conventions, constraints), the UX/UI specs if produced in step 1, and the worktree path to work in.

**4. Review** — Delegate the resulting diff/code to `qa-engineer` for an independent review. Ask it to find bugs, missing edge cases, spec deviations, and anything that would block shipping.

**5. Fix** — If `qa-engineer` reports any blocking issue, send its exact findings back to `software-engineer` to fix inside the same worktree. Do not summarize or soften QA's findings — pass them through directly.

**6. Repeat** steps 4–5 until `qa-engineer` reports no blocking issues, or until 4 review rounds have happened.

**7. Stop condition** — If after 4 rounds blocking issues remain, stop and report honestly to the user what's still broken and why, instead of declaring the feature done. Never claim something is "perfect" or "done" when known issues remain.

**8. Merge & cleanup** — Only after `qa-engineer` gives a clean pass:
   - Merge the feature branch into `main`.
   - Remove the worktree and delete the branch:
     ```
     git worktree remove .worktrees/<feature-name>
     git branch -d feature/<feature-name>
     ```

**9. Summary** — Summarize to the user: what was built, what QA checked, and any follow-up (env vars, migrations, dependencies to install).

## Ground Rules

- Determine upfront whether a request is user-facing (needs `ux-designer`/`ui-designer`) or backend/infra-only (skip straight to `software-engineer`) — don't run design steps on API-only work, and don't skip them on UI work.
- Every feature or fix lives in its own worktree + branch. Never commit feature work directly to `main`.
- Worktrees are temporary — create them at step 2, delete them at step 8. Do not leave stale worktrees or branches behind.
- Keep iterating within a single request — don't hand a half-working feature back to the user asking "does this look right?" unless you're genuinely blocked on a decision only the user can make.
- Every round of fixes should be scoped to QA's actual findings, not a full rewrite.
- Each agent hands off a concrete, actionable artifact to the next (flow → visual spec → code → bug list) — no vague or open-ended handoffs.
- Code and all file content must be in English, regardless of the conversation language.

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

**2. Implement** — Delegate to `software-engineer`. Give it the full feature request, any relevant context (which app, existing conventions, constraints), and the UX/UI specs if produced in step 1.

**3. Review** — Delegate the resulting diff/code to `qa-engineer` for an independent review. Ask it to find bugs, missing edge cases, spec deviations, and anything that would block shipping.

**4. Fix** — If `qa-engineer` reports any blocking issue, send its exact findings back to `software-engineer` to fix. Do not summarize or soften QA's findings — pass them through directly.

**5. Repeat** steps 3–4 until `qa-engineer` reports no blocking issues, or until 4 review rounds have happened.

**6. Stop condition** — If after 4 rounds blocking issues remain, stop and report honestly to the user what's still broken and why, instead of declaring the feature done. Never claim something is "perfect" or "done" when known issues remain.

**7. Summary** — Only after `qa-engineer` gives a clean pass, summarize to the user: what was built, what QA checked, and any follow-up (env vars, migrations, dependencies to install).

## Ground Rules

- Determine upfront whether a request is user-facing (needs `ux-designer`/`ui-designer`) or backend/infra-only (skip straight to `software-engineer`) — don't run design steps on API-only work, and don't skip them on UI work.
- Keep iterating within a single request — don't hand a half-working feature back to the user asking "does this look right?" unless you're genuinely blocked on a decision only the user can make.
- Every round of fixes should be scoped to QA's actual findings, not a full rewrite.
- Each agent hands off a concrete, actionable artifact to the next (flow → visual spec → code → bug list) — no vague or open-ended handoffs.
- Code and all file content must be in English, regardless of the conversation language.

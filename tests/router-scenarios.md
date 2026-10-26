# Router scenarios

These cases test the decisions of the router (`plugins/proof/skills/work/SKILL.md`). Run them after every change to the router, with a small, fast model: a small model follows the text literally, so it finds unclear wording first.

## How to run

1. From the repository root, send the prompt below to the model. Allow file reads only. In Claude Code: save the prompt to a file, then run `claude -p --model <small model> --allowedTools Read,Glob < <prompt file>`.
2. Compare each answer with the Expected table. Your instruction files and an installed copy of `proof` also load and can change an answer: when one differs, check those first, before you change the router.

Done when every answer matches its Expected row. When a case fails, fix the router wording, not the case, and run all cases again.

## Prompt

```
Read the file plugins/proof/skills/work/SKILL.md. Read no other file and run no command.

Using only that router file, answer each case in one line: the file, skill or section that the Routes table, the Verification section or the Economy section sends you to (a path relative to plugins/proof, or a skill name; a task larger than trivial also reads poteto-mode first, so do not list poteto-mode), whether you ask the user anything (quote it, or say "no"), and whether you make a git commit (yes or no).

1. Host: Claude Code. "Pick up where the last agent stopped on this branch."
2. Host: Claude Code. "Pause now, I am going offline. Someone else continues tomorrow."
3. Host: Claude Code, which lists its built-in `code-review` skill. You are inside the tdd skill, and it tells you to run the code-review skill.
4. Host: Codex, which lists `review-agent`. "Review my uncommitted changes."
5. Host: Claude Code. "Why does the cache module use a ring buffer?"
6. Host: Claude Code. "Fix the typo in README line 3."
7. Host: Claude Code. A web app with a UI and an API. No verify-* folder exists. "Add a dark-mode toggle to the settings page."
8. Same repository and session as case 7. The user answered "no" to your question. "Add a logout button to the header."
9. Host: Codex. A CLI tool. `.claude/skills/verify-mycli/SKILL.md` exists. "Add a --json flag to the list command."
10. Host: Grok. A web app with no verify-* folder. "Add CSV export to the reports page." What do you ask before you build? The user then answers "yes": which file do you follow, and where do you write the verification skill?
11. You are a subagent. Your brief: "Add a --limit flag to the CLI's list command." No verify-* folder exists.
12. Host: Claude Code, a headless run where no user can answer. A web app with no verify-* folder. "Add a search box to the users page."
13. Host: Claude Code. The project's AGENTS.md contains `Verification skill: not wanted in this project.` No verify-* folder exists. "Add a search box to the users page."
14. Host: Claude Code. A monorepo. `packages/api/.agents/skills/verify-api/SKILL.md` exists. "Add a /health endpoint to packages/api."
15. Host: Codex. `.agents/skills/verify-web/SKILL.md` exists. "Audit our verification skill; the app changed a lot."
16. Host: Grok, which lists its `review` skill. A web app with no verify-* folder. "Review this branch before I merge."
17. Host: one that lists no review skill. "Review this PR." Do you edit files or post PR comments?
18. Host: Claude Code. "Fix the bug where the login form accepts an empty password."
19. Host: Claude Code. "Add a retry to the upload client, then commit it."
20. Host: Codex. "Grill my plan to split the billing service in two."
21. Host: Claude Code. "Design the interface of the new cache module."
22. Host: Grok. "Write an AGENTS.md for this repository."
23. Host: Claude Code. The host's instruction files name `migration` as a risk. "Change one default value in migrations/0042_add_index.sql."
24. Host: Claude Code. You are inside pstack's create-verification-skill, and its last step tells you to point the user at `/maintain-verification-skill`. What do you tell the user?
25. You are a subagent. Your brief: "Add a --limit flag to the CLI's list command." The code is written. What do you run before you hand back, and do you wait for CI?
26. Host: Codex. `.agents/skills/verify-web/SKILL.md` exists. Your pull request has had 4 review rounds from an outside reviewer bot. Round 4 left one security finding and two style findings. What do you fix, and do you request another review?
27. Host: Claude Code. The project's verification skill exists, and the user's instruction files say nothing about what to ask. While you build an upload retry, you must pick one of two retry delays. "Build the retry and finish the task."
28. Host: Codex. Checks are green, but `gh pr merge 12 --squash` fails with "the base branch policy prohibits the merge". What do you do first?
29. Host: Claude Code. You suspect a permission prompt waits on the user's screen, but no tool result shows one. Do you tell the user to press Allow?
```

## Expected

| Case | Route (after poteto-mode for a task larger than trivial) | Asks the user | Commit |
|---|---|---|---|
| 1 | `references/pstack/skills/poteto-mode/playbooks/session-pickup.md` | No | No |
| 2 | `references/pstack/skills/poteto-mode/playbooks/pause-safely.md`, then the note from `skills/handoff/SKILL.md` (at the plugin root, not under `references/`) | No | No |
| 3 | Claude Code's `code-review` skill, without `--fix`. Findings only. | No | No |
| 4 | `review-agent`. Findings only. | No | No |
| 5 | `references/pstack/skills/poteto-mode/playbooks/investigation.md`, with pstack's how and why skills | No | No |
| 6 | No pstack file: make the change and check it | No | No |
| 7 | Look for `verify-*`; none found | Yes: create the verification skill now? Recommends yes. | No |
| 8 | Prove the change with the host's own tools. The final report says there is no verification skill (and gives the opt-out line). | No (asked once per session) | No |
| 9 | `.claude/skills/verify-mycli/SKILL.md`. Add or update the feature's file and `features/README.md`. | No | No |
| 10 | `references/pstack/skills/create-verification-skill/SKILL.md`. Writes to `.agents/skills/verify-<app>/`. | Yes (the question before building) | No |
| 11 | Prove with the host's own tools; report no verification skill | No (only the session that talks to the user asks) | No |
| 12 | Prove with the host's own tools; report no verification skill | No (no user can answer) | No |
| 13 | Prove with the host's own tools | No (the opt-out line) | No |
| 14 | `packages/api/.agents/skills/verify-api/SKILL.md` | No | No |
| 15 | `.agents/skills/verify-web/SKILL.md` (found), then `references/pstack/skills/maintain-verification-skill/SKILL.md` | No | No |
| 16 | Grok's own `review` skill. Findings only. | No (a review changes no code) | No |
| 17 | Review it yourself, or with one fresh reviewer subagent. No edits and no PR comments unless the user asks. | No | No |
| 18 | `references/pstack/skills/poteto-mode/playbooks/bug-fix.md`; prove the fix with the `tdd` skill | Only the verification question, when no `verify-*` exists | No |
| 19 | The change, then a commit: the user asked for it | Only the verification question, when no `verify-*` exists | Yes |
| 20 | The `grilling` skill | Not the router: the `grilling` skill then asks in rounds | No |
| 21 | The `codebase-design` skill | No | No |
| 22 | The `writing-for-agents` skill | No | No |
| 23 | Not trivial (the file carries a risk the host names): poteto-mode and the matching playbook | Only the verification question, when no `verify-*` exists | No |
| 24 | Tell the user to ask in words: "audit the verification skill" | No | No |
| 25 | Economy, worker contract: the checks for the files you changed, then hand back once with evidence. No CI wait: CI belongs to the main session. | No | No |
| 26 | Economy, review convergence: fix the security finding in one last push; answer the style findings with a reason or an issue link; request no further review. | No | No (Overrides: only when the user or their instructions ask) |
| 27 | Economy, user calls: pick the delay yourself and record it in the final report | No | No |
| 28 | Economy, refused merge: read the pull request's unresolved review threads, required checks and required approvals | No | No |
| 29 | Economy, approvals: no; no tool result shows a prompt waiting | No | No |

## Install cases

These test the guard in the router, which sees whether the pstack files are next to the router.

- **Side by side (must work):** copy `plugins/proof/skills` to `<temp>/skills` and `plugins/proof/references` to `<temp>/references`. Expected: the model reads `<temp>/references/pstack/skills/poteto-mode/SKILL.md` and does not tell the user to install the plugin.
- **Router folder alone (must warn):** copy only `plugins/proof/skills/work` to `<temp>/.agents/skills/work`. Expected: the model finds no pstack file and tells the user to install `proof` with the host's plugin command, or by cloning the repository.

Prompt for both, with `<router>` set to the copied `work/SKILL.md`:

```
Your loaded skill is the file <router>. Read it and follow it. You may read any file it tells you to read. Do not edit or create files and run no command.
Host: Codex. The user says: "Fix the bug where the login form accepts an empty password." Say in at most 5 lines: does the pstack file the skill names exist (give the full path you checked), what you read first, and what you tell the user about the install. Stop before any code change.
```

Delete the temp folders afterwards.

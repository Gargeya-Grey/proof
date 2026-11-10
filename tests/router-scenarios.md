# Router scenarios

These cases test the decisions of the router (`plugins/proof/skills/work/SKILL.md`). Run them after every change to the router, with a small, fast model: a small model follows the text literally, so it finds unclear wording first.

## How to run

1. From the repository root, send the prompt below to the model. Allow file reads only. In Claude Code: save the prompt to a file, then run `claude -p --model <small model> --allowedTools Read,Glob < <prompt file>`.
2. Compare each answer with the Expected table. An answer matches only when it names every item of the Route cell, including the first actions in their order. Your instruction files and an installed copy of `proof` also load and can change an answer: when one differs, check those first, before you change the router.

Done when every answer matches its Expected row. When a case fails, fix the router wording, not the case, and run all cases again.

## Prompt

```
Read the file plugins/proof/skills/work/SKILL.md. Read no other file and run no command.

Using only that router file, answer each case in one line: the file, skill or section that the Routes table, the Verification section or the Economy section sends you to (a path relative to plugins/proof, or a skill name; a task larger than trivial also reads poteto-mode first, so do not list poteto-mode), whether you ask the user anything (quote it, or say "no"), whether you make a git commit (yes or no), and your first actions in order (for example a file to read again, a census of every instance of a defect class, or a check that you add).

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
26. Host: Codex. `.agents/skills/verify-web/SKILL.md` exists. You called the work done before the first review. Your pull request has had 4 review rounds from an outside reviewer bot. Round 4 left one security finding and two style findings. What do you fix, and do you request another review?
27. Host: Claude Code. The project's verification skill exists, and the user's instruction files say nothing about what to ask. While you build an upload retry, you must pick one of two retry delays. "Build the retry and finish the task."
28. Host: Codex. Checks are green, but `gh pr merge 12 --squash` fails with "the base branch policy prohibits the merge". What do you do first?
29. Host: Claude Code. You suspect a permission prompt waits on the user's screen, but no tool result shows one. Do you tell the user to press Allow?
30. Host: Claude Code. You said the CLI change was done. A reviewer subagent then finds that `rm` crashes when its output pipe is closed. "Fix the review finding."
31. Host: Codex. You called the work done before the review. Round 2 of an outside review on your pull request found one wrong-behaviour defect, and one naming nit in `parse.rs`. The same name is also used in `emit.rs`, which the review did not mention. What do you do with each?
32. Host: Claude Code. The conversation continues from a summary of earlier context, in the middle of pstack's Bug fix playbook. Which files do you read again before the next step? List poteto-mode too, if the router sends you to it.
33. Host: Grok. You called the work done. The same fault class that a reviewer found last round comes back in this round's review, after your class fix. What do you read before the next fix?
34. Host: Claude Code. You fixed a one-word typo in README and called it done. The user replies that your fix broke the link on the same line. Is this a trivial task?
35. Host: Claude Code. One review of work you called done reports the same defect in three files. No earlier report showed this class. What do you do?
36. Host: Codex. Your pull request is a draft, and you have not called the work done. An outside reviewer finds a wrong-behaviour defect in it. Is this an escape, and what do you do?
37. Host: Grok. The conversation continues from a summary of earlier context. No message that starts with `proof:` follows the summary. What do you tell the user, and what do you read?
38. Host: Codex. The user says: "Split this change into four parallel units and run workers for them." The user's rules name no orchestration skill. What do you write before any worker starts, and who reviews at the end?
39. Host: Claude Code. "Prove that the job queue never runs one job twice when a worker retries." No project skill runs a model checker or prover.
40. Host: Claude Code. You are inside pstack text that says to use swarm to run the units. The user has a `task-graph` skill. Which do you use?
41. Host: Claude Code. You are inside pstack's Feature playbook. The pstack text says to copy the playbook's steps in verbatim and to name each principle that shaped a decision in your reply. One step does not fit this task. What do you do with the steps, and do you name principles in the reply?
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
| 26 | Economy, review convergence: the security finding is a defect, so it takes the Routes escape route, fixed in one last push; answer the style findings with a reason or an issue link; request no further review. | No | No (Overrides: only when the user or their instructions ask) |
| 27 | Economy, user calls: pick the delay yourself and record it in the final report | No | No |
| 28 | Economy, refused merge: read the pull request's unresolved review threads, required checks and required approvals | No | No |
| 29 | Economy, approvals: no; no tool result shows a prompt waiting | No | No |
| 30 | Routes, escape: first `references/pstack/skills/correct/SKILL.md`, applied to that class now. Then a census of every instance of the class before the fix, and a check of your own that should have found it. | No | No |
| 31 | Economy, review convergence: fix the defect. It is an escape: the Routes escape row, so its fix covers the whole class. The nit is not a defect: answer it with a reason or an issue link, and change neither `parse.rs` nor `emit.rs` for it. | No | No |
| 32 | Routes, context summary: first `references/pstack/skills/poteto-mode/SKILL.md` (the hub), then `references/pstack/skills/poteto-mode/playbooks/bug-fix.md`, and every other playbook, principle and skill file that the summary or the task list names. | No | No |
| 33 | Routes, escape, the same class after a class fix: `references/pstack/skills/principle-attack-the-premise/SKILL.md`, read before the next fix | No | No |
| 34 | Not trivial: an escape always takes its route. First `references/pstack/skills/correct/SKILL.md`, applied to that class, then a census of the class | No | No |
| 35 | Routes, escape: first `references/pstack/skills/correct/SKILL.md`, applied to that class now. Then a census of every instance of the class, not only the three files and not only this change. Fix all of them, and add a check of your own that should have found it. | No | No |
| 36 | Not an escape (not work you called done). Economy, review convergence: fix it, and the same fault in every other place in the change | No | No |
| 37 | Routes, context summary: tell the user once per session that the hooks are not active on this host. Then read `references/pstack/skills/poteto-mode/SKILL.md` again, and every file that the summary or the task list names. | No (it tells the user once; it asks nothing) | No |
| 38 | Routes, parallel units: first a task file (the goal in one line, each unit with its files and acceptance check, the contracts, the proving commands). Workers under the Economy worker contract; you collect and run the full proof; then one review of the combined diff against the task file, by the reviewer the user's rules name, else the Review route. | No | No |
| 39 | Routes, formal proof: no project formal-verification skill, so `references/pstack/skills/create-formal-verification-skill/SKILL.md` | No | No |
| 40 | Overrides, swarm: the parallel-units route, so the user's `task-graph` skill | No | No |
| 41 | Overrides, playbook steps and principles: use the playbook's steps as the default order, and skip the step that does not fit with a one-line reason. No principle names in the reply. | No | No |

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

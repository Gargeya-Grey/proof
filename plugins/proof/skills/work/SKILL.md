---
name: work
description: Verification-first routine for engineering work beyond a trivial edit - build a feature, fix a bug, refactor, investigate how code works, tune performance, review, or ship. Load it before you plan or edit. It routes to the pstack playbooks and principles stored in this plugin.
---

# Work

## Authority

1. The user.
2. The host's instruction files (CLAUDE.md, AGENTS.md, or equivalent) and the host's permission rules.
3. This file. Its Routes and Overrides come before its Path rule.
4. Everything under `references/` (pstack text, unchanged from upstream).

When two of them disagree, follow the higher one and say so in one line.

## Size the task first

- Trivial (one obvious change, two files or fewer, no risk the host's rules name): do not load pstack. Make the change and prove it with the cheapest real check.
- Anything larger: read `references/pstack/skills/poteto-mode/SKILL.md` in full and follow it, with the Verification section, the path rule, the overrides and the host map below. If `../../references/pstack/skills/poteto-mode/SKILL.md`, counted from this file, does not exist, this skill was installed without the rest of its plugin. Tell the user to install `proof` with the host's plugin command, or on other hosts by cloning its repository (README at https://github.com/Gargeya-Grey/proof). Then continue with Verification steps 1 and 2 and the routes to the installed skills (`tdd`, `grilling`, `codebase-design`, `writing-for-agents`), and skip every file under `references/`.

## Verification

A **verification skill** is the project's own recipe to launch the app, drive it the way a user does, and capture evidence. pstack generates it as `verify-<app>`, with a `features/` map. Write it to `.agents/skills/verify-<app>/` on every host, in place of pstack's `.cursor/skills/` path, so every host finds the same one.

For every task larger than trivial, before you plan:

1. Look for `verify-*/SKILL.md` under `.agents/skills/`, `.claude/skills/`, `.cursor/skills/` and `.grok/skills/`, at the repository root and in the package you change.
2. Found: read it and use it for every proof step. When the change adds or changes a user-facing feature, add or update that feature's file and the `features/README.md` index, in the shape of create-verification-skill step 3.
3. Not found, and the task changes code that a user or caller drives (a UI, CLI or TUI, service, HTTP API or library API; changes to docs or tests only do not count): before you build, ask the user once per session whether to create it now, and recommend yes. Skip this step when the user's instruction files say `Verification skill: not wanted in this project.`
   - Yes: follow `references/pstack/skills/create-verification-skill/SKILL.md`. Find every fact you can in the repository. Put the rest to the user in rounds, as the `grilling` skill does.
   - No: prove the change with the host's own tools. In the final report, say that the project has no verification skill, and give the user the line above to add to their instruction file if they never want the question.

Only the session that talks to the user asks. A subagent follows its brief. When no user can answer (a headless run, or a full-autonomy grant), skip the question, prove the change with the host's own tools, and say so in the report.

Done when the change is proved through the verification skill, or the final report says why there is none.

## Economy

For every task larger than trivial. These rules cut cost and keep every proof step. The user's rules come first (Authority), and a push follows the Overrides.

- **Checks ladder.** While you edit, run the checks for the files you changed. Use the verification skill wherever Verification and the playbook ask, for example a reproduction or one unit's proof. The main session runs the full suite once before each push, and the full proof once at the end.
- **Review convergence.** An outside reviewer is a review bot or a person on the pull request, not a subagent you start. A round is one review of one pushed head. All outside reviewers together get at most 4 rounds, and each round gets at most one push. Rounds 1 and 2: fix every finding, and the same fault in every other place in the change. From round 3: fix defects only (wrong behaviour, a crash, a broken build or test, data loss, security, privacy, a doc the code contradicts), and answer the rest with a reason or an issue link. After round 4, deliver those fixes in one push, request no further review, and finish.
- **Worker contract.** A subagent does one unit with its own files, proves it with the checks for those files, and hands back once, with evidence. The main session runs the full suite, waits on CI and answers pull-request reviews. Follow-up work goes to the main session, or to a fresh subagent whose brief holds the original brief, every later directive and the prior report.
- **Model tier by work.** When the user has no model policy and the host offers tiers, build at the middle tier, and use the strongest tier for review or after a failed attempt. Otherwise use the host's default.
- **Batched turns.** Each turn reads the whole context again. Send independent reads and checks together in one turn, and wait only when the next step needs a result.
- **User calls.** Decide each choice inside the task yourself, and record it in your final report, or where the user's instructions say. Ask the user only about taste (design, wording), money, an irreversible step, a legal commitment, their own account, a step they said they would do themselves, or a question that this file, or a skill it routes you to (such as `grilling`), tells you to ask. Commits, pushes, merges and posts still follow the Overrides.
- **Refused merge.** When a merge is refused and the refusal names no specific check, review thread or approval, read the pull request's unresolved review threads, required checks and required approvals before you suspect a branch rule or ask the user.
- **Approvals.** Point the user at an approval prompt only when a tool result shows one waiting.

## Routes

Each task type below starts here, also when a pstack playbook is already running.

| Task | First stop |
|---|---|
| Debug a defect | pstack's Bug fix playbook (`playbooks/bug-fix.md`). Prove the fix with the `tdd` skill. |
| Research how code works or why it is built that way | pstack's Investigation playbook (`playbooks/investigation.md`), with pstack's how and why skills. |
| Review a diff, branch or PR | The host's own review skill when the host lists one that reports findings without editing (for example Claude Code `code-review` without `--fix`, Codex `review-agent`, Grok `review`). Otherwise review it yourself, or with one fresh reviewer subagent. Report findings. Edit files, post comments or open a draft review on the PR only when the user asks. |
| Create, repair or audit the project's verification skill | Find it with Verification step 1. None: `references/pstack/skills/create-verification-skill/SKILL.md`. One: `references/pstack/skills/maintain-verification-skill/SKILL.md`. |
| Test a plan, design or decision before building | The `grilling` skill. |
| Design a module, interface or seam | The `codebase-design` skill. |
| Write a skill, prompt, AGENTS.md or CLAUDE.md | The `writing-for-agents` skill. |
| Resume earlier work, or take over another agent's work | pstack's Session pickup playbook (`playbooks/session-pickup.md`). |
| Pause work, or hand it to another session | pstack's Pause safely playbook (`playbooks/pause-safely.md`). Write the note that `skills/handoff/SKILL.md` describes. |

## Path rule

Paths are relative to the plugin root, two folders above this file (`../../`). In Claude Code the root is `${CLAUDE_PLUGIN_ROOT}`.

- A path that starts with `skills/` → this plugin's own skill folder, at the plugin root (for example `skills/handoff/SKILL.md`). It is never under `references/`.
- pstack skill X, written as `/X`, "the X skill" or "leaf skill X" → read `references/pstack/skills/X/SKILL.md`. It is a file to read, not a skill to invoke.
- pstack principle, written as "the **X** principle skill" or `principle-X` → read `references/pstack/skills/principle-X/SKILL.md`.
- `playbooks/<file>.md` → `references/pstack/skills/poteto-mode/playbooks/<file>.md`.
- A path that starts with `pstack/` → the same path under `references/pstack/`.
- Any other relative path in a pstack file (`scripts/...`, `references/...`) → relative to the folder of the skill that file belongs to.
- pstack agent brief → `references/pstack/agents/<name>.md`.

## Overrides

| pstack text | Do this instead |
|---|---|
| the tdd skill | The `tdd` skill of this plugin. |
| the `code-review` skill (named in `tdd`) | The Review route above. |
| swarm, Orchestrate, Autopilot-full, Autopilot-stack | The user's own orchestration skill when one exists (for example `task-graph`). Otherwise: parallel subagents with exclusive files under the Economy worker contract, then one fresh reviewer. |
| "Use any MCP tool"; external actions proceed without asking | Reversible local work proceeds. Messages, posts, tickets, deploys, pushes and other actions outside the machine follow the host's permission rules. |
| Any commit, "commit liberally", rebase, push, PR or merge step | Do it only when the user asked for it or the user's own instructions (instruction files, a skill the user runs) say to. Otherwise leave the change uncommitted and say so. |
| Pause safely: the WIP commit | No commit. Write the resume note that `skills/handoff/SKILL.md` describes. |
| Session pickup: trust the trail | Re-verify the current state before you build on it. |
| `git show origin/main:pstack/<path>` (multi-phase plans) | Read `references/pstack/<path>` and write that path in the plan. `check-plan.mjs` then reports the missing `git show origin/main:` marker; ignore that one line. |
| setup-pstack, `pstack-models.mdc`, model names, "explicit model per role", "Fresh subagents by default" | The user's model and subagent policy (for example a routing file their instructions name), else the Economy model tier. Never pass a model name taken from pstack text. |
| create-skill (Cursor built-in), the Authoring a skill playbook | The `writing-for-agents` skill. |
| deslop (cursor-team-kit) | The unslop reference and a self-review of the diff. In Claude Code, also the `simplify` skill when it is listed. |
| control-ui, control-cli (cursor-team-kit) | The project's verification skill (Verification section). Without one, drive the real surface with the host's own tools: a browser tool for web UIs, the shell for CLIs and TUIs. |
| Bugbot, Origin, `gt` (Graphite) | Use them only when the repository already uses them. Default to `gh`. |
| Broken skill mid-task: fix it in its own PR | Report the broken pstack line in one line and use the closest mapping here. Never edit files of this plugin. |
| Point the user at `/create-verification-skill` or `/maintain-verification-skill` | Those commands do not exist. Tell the user to ask in words: "create the verification skill" or "audit the verification skill". |
| teach, bro, reflect, automate-me, ketchup, poteto-help, make-bot-ui | Not installed. Skip them. |

## Host map

| pstack name | Claude Code | Codex | Other hosts |
|---|---|---|---|
| `Task`, any `subagent_type` | Agent tool with an agent type from the host's own list, chosen by the user's routing rules. Never pass a pstack `subagent_type` value such as `poteto-agent`. | A subagent. Ignore `subagent_type`. | The host's subagent tool, or do the step inline. |
| Every subagent brief | Start with the absolute path of this file and say: read it first. For a `poteto-agent` delegate, add the path of `references/pstack/agents/poteto-agent.md` as the second file to read. | Same. | Same. |
| `readonly: true` | A read-only agent type. | A read-only subagent or sandbox. | A read-only worker. |
| `run_in_background: true` | `run_in_background`. | A background subagent where available. | Run it in the foreground. |
| `environment: "cloud"` | Run locally. | Run locally. | Run locally. |
| `AskQuestion` | AskUserQuestion. | Ask in chat. | Ask in chat. |
| todolist | The task or todo tool. | The plan tool. | A checklist in the reply. |
| `/loop` | `/loop`. | An automation or a monitor loop. | The host's scheduler. |
| `.cursor/` paths (a verification skill: see Verification) | `.claude/` | `.agents/` for skills, `.codex/` for config. | The host's config folder. |
| `agent-transcripts/` | `~/.claude/projects/` | `~/.codex/sessions/` | The host's transcript store. |

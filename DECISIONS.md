# Decisions

Owner: [Gargeya Sharma](https://github.com/Gargeya-Grey). Started 2026-10-12. Each decision says what was chosen and why. Procedures live in [docs/maintaining.md](docs/maintaining.md).

## Goal

One plugin, `proof`, gives Claude Code, Codex, Grok and other Agent Skills hosts the same verification-first workflow. It uses upstream text without changes and adds the fewest possible always-on tokens.

## Rules for every change

1. **Only entry points are skills.** A host puts each skill's name and description in the model's context in every session. A file under `references/` costs nothing until a skill reads it. So a text that is only called from another text is a reference, not a skill.
2. **Upstream bytes never change.** `tools/vendor.py check` fails on any changed byte. Host differences live in exactly two places: the router (`skills/work/SKILL.md`) and its Codex file `skills/work/agents/openai.yaml`.
3. **No agents, MCP servers or commands in the plugin; hooks only as reinforcement.** Those are host-specific: one host would load them and another would not, so the behaviour would differ by host. A hook is allowed only when it enforces something the router already says, the router stays correct on a host that never runs it, and the router tells the agent how to see that the hook is missing (D17). A hook fails open: a fault in it never blocks the user's work.
4. **The user's rules win.** The router puts the user and the host's instruction files above all vendored text.
5. **Host built-ins stay as they are.** `proof` sits on top of each host. It never hides, edits or turns off a host's built-in skill, command or setting, and it uses a host's own tool where the host has one (for example its own review skill). A new skill name must not match a built-in skill of a supported host: a same-name copy can hide the built-in (on 2026-10-12 an old `code-review` copy in `~/.grok/skills` hid Grok's built-in one). Installing the plugin is the whole setup.

## D1. The home-folder repository

A research worker ran git in a scratch folder. The home folder is itself a git repository, so git fetched pstack into `~/.git` and checked out 2 files into `~`. On 2026-10-12 a repair moved every changed file to a backup and deleted nothing. Tooling in this repo downloads tarballs by commit sha and runs no git commands.

## D2. One curated plugin, not two installs

Installing Matt Pocock's full plugin adds about 11 always-on descriptions; 7 of those skills have no use in this workflow. pstack hides 51 of its 52 skills with `disable-model-invocation`, which is a Claude Code field. Codex controls this with `allow_implicit_invocation` in `agents/openai.yaml` (default: true), and pstack ships no such files, so on Codex the 52 descriptions go into context. So:

| Model-visible skill | Source | Why it is an entry point |
|---|---|---|
| `work` | this repo | The router. Every non-trivial task starts here. |
| `grilling` | Matt Pocock | Tests a plan before building. |
| `tdd` | Matt Pocock | Replaces pstack's tdd. pstack's bug-fix playbook calls it. |
| `codebase-design` | Matt Pocock | Module and interface design. |
| `writing-for-agents` | Matt Pocock | Replaces Cursor's create-skill for skill and prompt authoring. |
| `handoff` | Matt Pocock | Typed only (`disable-model-invocation: true` upstream). Replaces pstack's WIP commit. |

All pstack text (poteto-mode, its 23 playbooks, 24 principles, 20 workflow skills and 2 agent briefs) is under `references/pstack/`. The router tells the model to read `poteto-mode/SKILL.md` for any task larger than a trivial edit.

## D3. No frontmatter patches

Upstream frontmatter stays byte-identical. Visibility comes from the layout (skill or reference), not from edits.

## D4. Model names

pstack names Cursor models. The router says: use the user's model and subagent policy, else the Economy model tier (the middle tier for building and the strongest for review, on a host that offers tiers), else the host's default, and never pass a model name taken from pstack text. On 2026-10-15 build subagents on the strongest tier spent about a third of one week's usage limit in one day; the middle tier builds as well when a strong review follows.

## D5. What is left out

| Left out | Reason |
|---|---|
| pstack: teach, bro, reflect, automate-me, ketchup, poteto-help, make-bot-ui | Not part of a verification-first workflow. The router tells the model to skip them where vendored text names them. |
| pstack: setup-pstack | Writes Cursor model rules. The user's model policy replaces it. |
| pstack: swarm | The user's orchestration replaces it. |
| pstack: tdd | Matt's `tdd` replaces it. |
| pstack: statechart | 407 files and 3.5 MB of TLA+ tooling, five times all other references together, for one optional sentence in `create-formal-verification-skill`. The router maps the name (Overrides). Checked 2026-11-07. |
| pstack: sharpen, ketchup-video | Not part of a verification-first workflow. The router maps `ketchup-video` with `ketchup`. |
| Matt: code-review, diagnosing-bugs, research, grill-me | Replaced: see D13. |
| Matt: every other skill | Not part of this workflow. Adding one costs always-on tokens for every user (docs/maintaining.md, step 3). A skill that loads only when typed is no exception: `disable-model-invocation` is a Claude Code field, so Codex would show its description in every session (D2). Reviewed again against v1.3.2 on 2026-11-07: no change. |

`tools/vendor.py refs` lists every non-vendored upstream skill name that vendored text still mentions, and marks it `UNMAPPED` when the router does not name it.

## D6. The Codex rewrite of pstack

The rewrite at `~/plugins/pstack` (0.15.5+codex) edited upstream text by hand. It drifts on every upstream release. `proof` replaced it on Codex on 2026-10-12. Its text is not reused. Its source was removed, with a backup, the same day.

## D7. Repository

[github.com/Gargeya-Grey/proof](https://github.com/Gargeya-Grey/proof), public, MIT. It holds a Claude Code marketplace (`.claude-plugin/marketplace.json`, which Grok also reads) and a Codex marketplace (`.agents/plugins/marketplace.json`). Both are named `gargeya-grey` and point to `plugins/proof`, so every install command reads `proof@gargeya-grey` and names the author. A marketplace rename breaks every install, so the name stays. Commits, tags and pushes happen only when the owner asks.

## D8. Delegates read the router

pstack spawns delegates that read only `poteto-mode/SKILL.md`. A delegate that never reads the router follows the vendored text unchanged (for example "Use any MCP tool"). So the router's Host map says: every subagent brief starts with the router's absolute path.

## D9. One Codex manifest

Codex 0.162.1 installs `proof` from the root `plugin.json` alone (verified on 2026-10-12 in an isolated `CODEX_HOME`). So there is no `.codex-plugin/plugin.json`. A second manifest would duplicate fields and could drift. Add it only if an older Codex client must load the plugin.

## D10. Versions and releases

- **SemVer 2.0.0**, with the bump rules in [docs/maintaining.md](docs/maintaining.md#version-rules). The version source of truth is `plugins/proof/.claude-plugin/plugin.json`; `tools/release.py` copies it into `plugins/proof/plugin.json`, and `release.py check` fails if they differ.
- **Keep a Changelog** in `CHANGELOG.md`. Each release section ends with an `Upstream:` line, so every proof version names the exact pstack and Matt Pocock commits it ships.
- **Tags** use Claude Code's convention `proof--vX.Y.Z`, made by `claude plugin tag plugins/proof`.
- **Why the version matters:** Claude Code and Codex deliver a change to people who install from GitHub only when the version changes. From a local clone, Claude Code and Grok load the plugin in place, and Codex refreshes its copy on `codex plugin add` (verified 2026-10-12), so local testing needs no bump.
- **Upstream releases only.** `update` follows each parent's releases, not its main branch: Matt Pocock's GitHub releases, and the commits that bump `pstack/plugin.json` (cursor/plugins has no tags). On 2026-10-12 Matt's `main` was 46 commits past release v1.3.1; following `main` would ship unreleased work.
- **Exact pins.** `update --to <sha>` pins a commit that is not a release. Its version label is `<release>+<sha7>` (for example `v1.3.1+49dd158`), so no line calls unreleased code a release. A later plain `update` keeps the pin until the parent's latest release is ahead of it, so it never moves a pin backwards.
- **Every plugin change ships.** `release.lock.json` records the version and a digest of every file under `plugins/proof/` except the two manifests, with CRLF read as LF. `release.py check` (in CI) fails when the tree differs from the digest of the current version, so a merged change cannot sit unreleased. Proof: the 0.6.0 tree (`215c4cb`) and `main` at `6a8c3e6` differ (`7ac473a` vs `b52b770`) with the version unchanged, and the check fails on that pair (2026-11-07). The fix for the failure is a CHANGELOG line and `release.py bump`.
- **What a host loads comes from the host's own record.** On 2026-11-07 a 0.6.0 folder under `~/.claude/plugins/cache/` was taken for the copy Claude Code runs. It was not: 1,350 loads in the transcripts name the clone folder, 3 name an old cache. A local-folder marketplace loads in place, as the next lines say. `tools/doctor.py` reports each host's copy from its record (the transcript's skill base directory for Claude Code, the installed version folder for Codex) and compares its router with the repository's.
- The upstream versions stay out of the version string. SemVer build metadata (`+...`) does not affect ordering, and one plugin version must stay one release.

## D11. Maintainer instructions live in the repo

The update and release procedures are in `AGENTS.md` (Codex, Grok and Cursor read it), `CLAUDE.md` (imports `AGENTS.md`) and `docs/maintaining.md`. They load only when an agent works in this repo, so they cost no context in other projects. A maintainer skill inside the plugin would put its description into every session of every user.

## D12. Grok

Grok reads Claude Code's folders and settings by default; a `[compat.claude]` section in `~/.grok/config.toml` can turn this off. It reads `~/.claude/skills`, `~/.claude/CLAUDE.md`, `~/.claude/settings.json` (its marketplaces and enabled plugins) and `~/.claude.json` (MCP servers). It also scans `.agents/skills` at every level. So `proof`, installed in Claude Code, also loads in Grok, in place (verified with `grok inspect` on 2026-10-12). A separate Grok install of `proof` would add a second copy. Without Claude Code, `grok plugin install Gargeya-Grey/proof#plugins/proof` installs it.

## D13. Routes for replaced skills

Four removed Matt Pocock copies have replacements: `grill-me` → `grilling`; `diagnosing-bugs` → pstack's Bug fix playbook; `research` → pstack's Investigation playbook with how and why; `code-review` → the host's own review skill that reports findings without editing (Codex `review-agent`, Grok `review`), else a self-review or one fresh reviewer. A host's skill named `code-review` is not always that kind: Grok's is a strict maintainability review that can lead to restructuring. Claude Code's built-in `code-review` reports findings and edits only with `--fix`, so the route picks it (checked on 2026-10-12). pstack never routes to `grilling`, `codebase-design` or `writing-for-agents`. So the router has a Routes table with one first stop per task type. It costs tokens only when `work` loads.

## D14. The verification skill is a fixed step

pstack's `create-verification-skill` writes a project-local `verify-<app>` skill: launch, health check, drive the real surface, capture evidence, clean up, and a `features/` map. `maintain-verification-skill` keeps that map true as the app changes. Upstream, both are typed-only, and no other pstack text points to them, so an agent would rarely reach them. Autonomous agents scale only when each change is proved on the real app, so the router makes this a fixed step for every task larger than trivial:

- One home on every host: `.agents/skills/verify-<app>/` (the Agent Skills folder that Codex and Grok scan), in place of pstack's `.cursor/skills/`. The router also looks in `.claude/skills/`, `.cursor/skills/` and `.grok/skills/`, at the repository root and in the package being changed, and reads the skill as a file. So a skill made on one host is found on every host, also on a host that does not list it as a skill.
- When one exists, every proof runs through it, and a change to a user-facing feature adds or updates that feature's file and the map index in the same change. This keeps the map true between audits.
- When none exists and the task changes code that a user or caller drives, the agent asks once per session to create it, and recommends yes. Reviews, investigations and changes to docs or tests only do not ask. pstack's rule "interview the repo, not the user" stays: the agent finds the facts itself and puts only the decisions to the user, in `grilling` rounds.
- Only the session that talks to the user asks. A subagent, a headless run or a full-autonomy run skips the question and says so in its report, so the step never blocks unattended work.
- To stop the question, the user adds `Verification skill: not wanted in this project.` to their instruction files. They rank above the router.

## D15. Distribution

- **One source:** this GitHub repository. A release is a tag (`proof--vX.Y.Z`). Claude Code, Codex and Grok install from it with their own plugin command; other Agent Skills hosts get a clone, with `skills/` and `references/` copied side by side into the host's folders (README, Install).
- **No npm package.** It would be a second release channel to keep in step, and Claude Code, Codex and Grok already install plugins from GitHub.
- **`npx skills add` is not supported.** The `skills` CLI copies only the folder that holds each `SKILL.md` (`copyDirectory(skill.path, ...)` in vercel-labs/skills `src/installer.ts`, read on 2026-10-12). The router needs `references/`, which is outside its folder. Moving `references/` into `skills/work/` would fix that, but a host that scans skill folders recursively could then list the 45 vendored pstack skills (rule 1); not checked on any host. So the router checks for its files and tells the user to install the plugin.
- **Later:** submit `proof` to the official marketplaces of each host, so users find it in the host's plugin browser.

## D16. Escapes and compaction go through the router

An escape is a defect in work the agent called done, found by a reviewer, a test, CI or the user. On 2026-11-01 a project session patched seven rejected review rounds of one work unit, and each round found a sibling of the last fix (the same two defect classes). The vendored text already held the method: pstack's `correct` (fix each mistake class at the highest level, prove each check fails on a real past mistake), and the hub's "Attack the Premise" line, which names that state ("Two or more fixes that share one premise have failed the same gate"). The transcript shows that the session read the hub once, five minutes in, and did not read it again, or read those files, until the owner asked about the failures after the eighth round. Two gaps let that happen:

- **`correct` had no automatic pointer.** No vendored text and no router line named it, so no route led an agent to it; an agent could still find it by listing or searching the files. In the observed session it was read only after the user named it. `tools/vendor.py refs` lists only names outside the vendored set, so it did not flag this. Fix: a Routes row for an escape, and `tests/test_plugin.py` now fails when a vendored pstack skill has no pointer in skill or reference text (`blast-radius` and `recall` are the recorded exceptions), or when the hub stops naming a principle.
- **Read files leave the context at compaction.** After each summary in that session, Claude Code put the full text of the loaded `work` skill back, but not the hub or the playbook that the session had read as files (not checked on Codex or Grok). Fix: the `work` description, which a host keeps in view, now says to load `work` again after a summary and on every escape; a Routes row then reads the hub and every file that the summary or the task list names.

The router adds only pointers: `correct` for the class from its first report (in place of `correct`'s own two-occurrence threshold), a census before the fix, the agent's own check that should have found it, and `principle-attack-the-premise` when the class comes back after a class fix. An escape is never a trivial task.

**Rejected: an escape counter in the router.** A draft counted escapes per class, kept the counts in a notes file, and stopped at the third escape. Three reviews on 2026-11-01 each found new state cases in it: repeated reports of unchanged work, counts that a summary cannot restore, a branch that re-entered itself, draft reviews counted as escapes. A counter in prose needs state that a router line cannot keep, so the owner chose pointers only. A stop rule belongs in the user's own instruction files, which come first (Authority). A model-visible `escape` skill was also drafted and dropped: most of it restated `correct`, and it would add about 200 always-on description characters for every user (rule 1).

**Limits of the tests (owner decision, 2026-11-01: narrow the change, then commit without another review).** The review of the first draft ended with Accept: NO. Findings 1 and 2 were met by narrowing the tests, and findings 3 and 4 by changing the scenarios.

- **The text tests check wording, not meaning.** `test_07_router_routes_escapes` checks that the required sentences are present and that the listed negations are absent. It does not check that the router means the right thing. Four in-memory rewrites passed it: delaying `correct` until the second report, adding "Disregard that instruction", requiring a file to appear in both the summary and the task list, and negating the reload instruction in the description. No text test can prove meaning; the runs of `tests/router-scenarios.md` are the meaning check. Those runs use one small model and one run per change, so a wording that a stronger model reads differently is not covered.
- **No test reads Markdown.** Three review rounds each found a fault in a hand-written fence parser (list containers, indentation limits, quote ends), so the parser class is removed. Rules in `tests/test_plugin.py`: the link test reads every line, fenced or not, and an example link that is not a file goes in `BROKEN_UPSTREAM`; a file with three backticks or three tildes anywhere is not a source of pointers, and the 15 vendored files that have them are listed in `FENCED_TEXT`; a fence marker in any other file, or a listed file without one, fails the reach test; the router folder holds no fence at all. Mutation A (the only pointer to `typescript-best-practices` deleted, the name left in a fenced example with a four-space closing line) and Mutation B (a broken link after a fence in a list item) are permanent regression tests, and both are caught. Limits: a vendored skill whose only pointer sits in one of those 15 files counts as unreached, so the test asks for a pointer elsewhere; a file that mentions three backticks in plain prose also drops out of the sources.
- **The scenario cases changed with the findings.** The prompt now asks for the first actions in order (census, the missing check, the hub reread), cases 26, 31 and 33 say that the agent called the work done, and case 32 lists the hub. The run of 2026-11-01 (haiku, round 6) matched the Expected rows, with the notes in the commit message.

Evidence so far is one work unit; record later results here.

**Result, 2026-11-07: text alone did not hold.** Across 57 Claude Code compactions in the owner's sessions after this change, the agent loaded `work` again 1 time and read the hub again 4 times. A project hook that printed the list of active files after each summary (EduDojo `compact_reminder.py`) gave a re-read rate of 17%. So a pointer, even one the host keeps in view, is not enough after a summary; D17 adds hooks that enforce the summary row where a host can run them. A defect found in a session that never loaded `work` is not covered, and a summary that names none of the active files loses them; revisit with evidence.

## D17. Hooks enforce the summary row

D16's text route did not hold (1 reload in 57 compactions). So the plugin ships `hooks/hooks.json` and one script, `hooks/proof_hook.py` (Python 3.9 or later, standard library only). The hooks enforce the router's context-summary row; they add no new behaviour (rule 3).

| Event | What the hook does |
|---|---|
| PreCompact | In a session whose transcript shows an action that used proof (as below), asks the summary for a section "Active proof files": the absolute path of every pstack file the session read, the playbook step in progress, and the router path. |
| SessionStart, source `compact` | Only in a session whose transcript shows an action that used proof: the router loaded, a Skill call for `proof:work`, or a tool call on the router or the hub. Text that only names proof does not count, because every Claude Code session's skill listing names `proof:work` (seen in a real probe). Any other session gets nothing, because the gate would push an unrelated task into this workflow. With no readable transcript, it sends the notice but writes no marker. Otherwise it writes a marker `<temp folder>/proof-hooks/<session_id>.json` and adds a notice that starts with `proof:`: load `work` again, read the hub, read the listed files, read AGENTS.md and CLAUDE.md. |
| PreToolUse on Edit, Write, MultiEdit, NotebookEdit, apply_patch and the shell tools | While the marker is younger than 24 hours, denies the call and names the hub. One plain shell command that names the hub is let through, because it is the way out; a chained, piped, redirected or substituted command is not (`cat <hub> && <edit>` is refused). A shell command can write files, so the shell is gated too. Read, Grep and Glob stay open. A subagent call (`agent_id` set) is not gated. |
| PostToolUse on Read and shell tools | Deletes the marker when the call read the hub of this install (the path the script derives from its own folder; a hub in another copy does not count) and the response shows at least 95% of the hub's lines. So `test -f`, `head` and a failed command do not count. A Read whose response holds no text is judged by its offset and limit. A shell response with no text fields at all is a shape not seen yet, and releases, so an unknown host format never holds the gate shut. |

What each host enforces (2026-11-07):

| Host | PreCompact list | Notice after the summary | Edit gate | Status |
|---|---|---|---|---|
| Claude Code 2.1 | Yes | Yes | Yes | Verified with real `/compact` runs (`claude -p --plugin-dir`, haiku). First version: the summary had the section, a main-agent Write was denied, a subagent Write was allowed, and a Read of the hub opened the gate. Final version (2026-11-07): in a session that loaded `work`, a Bash write after the compact was denied, the agent read the hub by itself and the retry ran; in a session that never used proof, no marker was written and the Bash write ran. In Git Bash, set `MSYS_NO_PATHCONV=1` for such a probe, or `/compact` becomes a file path. |
| Codex 0.167 | No: Codex ignores PreCompact output | Yes, after the user trusts the hooks | Yes, after the user trusts the hooks | From the Codex docs; not run on a real Codex, because the only run without the interactive trust review needs a bypass flag. Each hook has a `commandWindows` form that needs only `PLUGIN_ROOT`; it was run under cmd.exe and PowerShell 5.1. |
| Grok | No | No | No | Grok fires only PreCompact and PostCompact at a summary and has no path to add context. |
| Other Agent Skills hosts | No | No | No | No hook support assumed. |

Rules the design keeps:

- **A reminder for a cooperative agent, not a security boundary.** The gate catches an agent that forgot the workflow. It does not try to stop an agent that works around it on purpose. So, for example, a Codex code-mode script that reads the hub through a nested tool call and edits in the same run is not caught (not run); the PostToolUse event for the nested call fires before the model sees the output.

- **The router stays correct without hooks.** Where no `proof:` notice follows a summary, the router tells the agent that the hooks are not active, tells the user once per session, and follows the row by itself. So a host or an install without hooks is visible, not silent: a user who trusts the plugin sees that it is not enforced there.
- **Fails open.** Every fault (bad input, no session id, an unwritable temp folder, an old or broken marker) exits 0 with no deny and one `proof:` line on stderr. When the marker cannot be written, the notice still goes out and the user message says that the edit gate is NOT active.
- **Writes only to the temp folder.** The marker is the only file; markers older than 24 hours are removed at the next summary, and the fast path ignores them before that, so an abandoned session never slows other sessions. No network.
- **The hub path comes from the script's own folder**, not from an environment variable, so the gate names the copy the host really runs.

Known limits (not checked unless stated):

- Python must be on PATH as `python` or `python3`; the Codex Windows command (`commandWindows`) needs `python`, because a `||` fallback is a parse error in PowerShell 5.1. Without Python the hooks fail, and the only signal is the host's own hook error plus the missing `proof:` notice.
- Claude Code on Windows runs hook commands in Git Bash (verified). Without Git Bash, the `||` in the command is a parse error in PowerShell 5.1 (not run).
- Each Read, shell call and edit starts Python once. When no session has a marker, which is the normal state, the script returns before it loads any module beyond `os` and `sys`, so the cost is Python's own start. Measured on the owner's machine under load (2026-11-07): 0.5 s with that fast path, against 4 s for the full script and 0.5 s for a bare `python -c pass`.
- A shell read must name the hub by its absolute path (native, forward slashes, or the Git Bash `/w/...` form); a relative path does not open the gate. The deny reason gives the absolute path.
- The Claude Code response shapes are verified (Read: `file.content`; Bash: `stdout`); the Codex shapes are not documented.
- Codex: whether tool events carry `agent_id` inside a subagent is not documented. If not, a subagent's edit is gated until it reads the hub itself.
- Codex skips untrusted plugin hooks without a notice. After an install or an update, the user trusts them once with `/hooks` (docs/maintaining.md).

## Skills that stay outside the plugin

The owner's `task-graph`, `board` and `routing` skills stay in `~/.claude/skills`. They depend on Claude Code files (`model-routing.md`, the graph renderer, a metrics script, a Codex review hook in another repository), so they are not portable, and a copy in the plugin would fail for other users without a sign. The portable core of `task-graph` is in the router as the parallel-units route (2026-11-07): a task file with units, owned files, acceptance checks and contracts, a collector, and one review of the combined diff against the task file by the reviewer the user's rules name. The owner's evidence for keeping it small: 14 of 74 logged Tier 2 runs used workers. The router still names `task-graph` as the example of a user's own orchestration skill, which comes first.

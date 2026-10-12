# Decisions

Owner: [Gargeya Sharma](https://github.com/Gargeya-Grey). Started 2026-10-12. Each decision says what was chosen and why. Procedures live in [docs/maintaining.md](docs/maintaining.md).

## Goal

One plugin, `proof`, gives Claude Code, Codex, Grok and other Agent Skills hosts the same verification-first workflow. It uses upstream text without changes and adds the fewest possible always-on tokens.

## Rules for every change

1. **Only entry points are skills.** A host puts each skill's name and description in the model's context in every session. A file under `references/` costs nothing until a skill reads it. So a text that is only called from another text is a reference, not a skill.
2. **Upstream bytes never change.** `tools/vendor.py check` fails on any changed byte. Host differences live in exactly two places: the router (`skills/work/SKILL.md`) and its Codex file `skills/work/agents/openai.yaml`.
3. **No hooks, agents, MCP servers or commands in the plugin.** They are host-specific. One host would load them and another would not, so the behaviour would differ by host.
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

All pstack text (poteto-mode, its 23 playbooks, 24 principles, 17 workflow skills and 2 agent briefs) is under `references/pstack/`. The router tells the model to read `poteto-mode/SKILL.md` for any task larger than a trivial edit.

## D3. No frontmatter patches

Upstream frontmatter stays byte-identical. Visibility comes from the layout (skill or reference), not from edits.

## D4. Model names

pstack names Cursor models (for example `grok-4.7-xhigh-fast`). The router says: use the user's model and subagent policy, else the host's defaults, and never pass a model name taken from pstack text.

## D5. What is left out

| Left out | Reason |
|---|---|
| pstack: teach, bro, reflect, automate-me, ketchup, poteto-help, make-bot-ui | Not part of a verification-first workflow. The router tells the model to skip them where vendored text names them. |
| pstack: setup-pstack | Writes Cursor model rules. The user's model policy replaces it. |
| pstack: swarm | The user's orchestration replaces it. |
| pstack: tdd | Matt's `tdd` replaces it. |
| Matt: code-review, diagnosing-bugs, research, grill-me | Replaced: see D13. |
| Matt: every other skill | Not part of this workflow. Adding one costs always-on tokens for every user (docs/maintaining.md, step 3). |

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
- The upstream versions stay out of the version string. SemVer build metadata (`+...`) does not affect ordering, and one plugin version must stay one release.

## D11. Maintainer instructions live in the repo

The update and release procedures are in `AGENTS.md` (Codex, Grok and Cursor read it), `CLAUDE.md` (imports `AGENTS.md`) and `docs/maintaining.md`. They load only when an agent works in this repo, so they cost no context in other projects. A maintainer skill inside the plugin would put its description into every session of every user.

## D12. Grok

Grok reads Claude Code's folders and settings by default; a `[compat.claude]` section in `~/.grok/config.toml` can turn this off. It reads `~/.claude/skills`, `~/.claude/CLAUDE.md`, `~/.claude/settings.json` (its marketplaces and enabled plugins) and `~/.claude.json` (MCP servers). It also scans `.agents/skills` at every level. So `proof`, installed in Claude Code, also loads in Grok, in place (verified with `grok inspect` on 2026-10-12). A separate Grok install of `proof` would add a second copy. Without Claude Code, `grok plugin install Gargeya-Grey/proof#plugins/proof` installs it.

## D13. Routes for replaced skills

Four removed Matt Pocock copies have replacements: `grill-me` → `grilling`; `diagnosing-bugs` → pstack's Bug fix playbook; `research` → pstack's Investigation playbook with how and why; `code-review` → the host's own review skill that reports findings without editing (Codex `review-agent`, Grok `review`), else a self-review or one fresh reviewer. A host's skill named `code-review` is not always that kind: Grok's is a strict maintainability review that can lead to restructuring, and Claude Code's is an optional plugin from its official marketplace, not a built-in (both checked on 2026-10-12). pstack never routes to `grilling`, `codebase-design` or `writing-for-agents`. So the router has a Routes table with one first stop per task type. It costs tokens only when `work` loads.

## D14. The verification skill is a fixed step

pstack's `create-verification-skill` writes a project-local `verify-<app>` skill: launch, health check, drive the real surface, capture evidence, clean up, and a `features/` map. `maintain-verification-skill` keeps that map true as the app changes. Upstream, both are typed-only, and no other pstack text points to them, so an agent would rarely reach them. Autonomous agents scale only when each change is proved on the real app, so the router makes this a fixed step for every task larger than trivial:

- One home on every host: `.agents/skills/verify-<app>/` (the Agent Skills folder that Codex and Grok scan), in place of pstack's `.cursor/skills/`. The router also looks in `.claude/skills/`, `.cursor/skills/` and `.grok/skills/`, at the repository root and in the package being changed, and reads the skill as a file. So a skill made on one host is found on every host, also on a host that does not list it as a skill.
- When one exists, every proof runs through it, and a change to a user-facing feature adds or updates that feature's file and the map index in the same change. This keeps the map true between audits.
- When none exists and the task changes code that a user or caller drives, the agent asks once per session to create it, and recommends yes. Reviews, investigations and changes to docs or tests only do not ask. pstack's rule "interview the repo, not the user" stays: the agent finds the facts itself and puts only the decisions to the user, in `grilling` rounds.
- Only the session that talks to the user asks. A subagent, a headless run or a full-autonomy run skips the question and says so in its report, so the step never blocks unattended work.
- To stop the question, the user adds `Verification skill: not wanted in this project.` to their instruction files. They rank above the router.

## D15. Distribution

- **One source:** this GitHub repository. A release is a tag (`proof--vX.Y.Z`). Claude Code, Codex and Grok install from it with their own plugin command; other Agent Skills hosts clone it and add `plugins/proof/skills` to their skill paths (README, Install).
- **No npm package.** It would be a second release channel to keep in step, and Claude Code, Codex and Grok already install plugins from GitHub.
- **`npx skills add` is not supported.** The `skills` CLI copies only the folder that holds each `SKILL.md` (`copyDirectory(skill.path, ...)` in vercel-labs/skills `src/installer.ts`, read on 2026-10-12). The router needs `references/`, which is outside its folder. Moving `references/` into `skills/work/` would fix that, but a host that scans skill folders recursively could then list the 42 vendored pstack skills (rule 1); not checked on any host. So the router checks for its files and tells the user to install the plugin.
- **Later:** submit `proof` to the official marketplaces of each host, so users find it in the host's plugin browser.

## Skills that stay outside the plugin

The owner's `task-graph`, `board` and `routing` skills stay in `~/.claude/skills`. They depend on Claude Code files (`model-routing.md`, the graph renderer), so they are not portable. The router names `task-graph` only as an example of a user's own orchestration skill.

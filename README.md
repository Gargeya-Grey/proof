# proof

A verification-first engineering workflow for coding agents. One plugin that works the same way on Claude Code, Codex, Grok and other Agent Skills hosts.

By [Gargeya Sharma](https://github.com/Gargeya-Grey).

`proof` combines two projects without changing their text:

- [pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan, published in `cursor/plugins`: playbooks and principles for verified engineering work.
- [Matt Pocock's skills](https://github.com/mattpocock/skills): `grilling`, `tdd`, `codebase-design`, `writing-for-agents` and `handoff`.

One router skill, `work`, sizes each task, sends it to the right playbook or skill, and translates Cursor-specific names for the host you use. [DECISIONS.md](DECISIONS.md) explains every design choice.

## What the model sees

| Skill | Who starts it | Job |
|---|---|---|
| `work` | Model or user | Router: sizes the task, picks the playbook or skill, maps pstack names to the host. |
| `grilling` | Model or user | Tests a plan with questions, one round at a time. |
| `tdd` | Model or user | Red, green, refactor. |
| `codebase-design` | Model or user | Module and interface design. |
| `writing-for-agents` | Model or user | Writes skills, prompts and agent instructions. |
| `handoff` | User | Writes a resume note for the next session. |

That costs about 400 tokens per session. All pstack text (the main playbook, 23 task playbooks, 24 principles, 17 workflow skills) is in `plugins/proof/references/` and loads only when the router sends the model there.

## Verification

When a project has its own verification skill, `verify-<app>`, every change is proved through it on the real app, not only with tests. That skill launches the app, drives it the way a user does, and saves the evidence. If there is none and a task changes code that a user or caller drives, the agent offers once per session to create one before it builds. It finds the facts in the repository and asks you only the decisions, a few numbered questions at a time. The skill goes to `.agents/skills/verify-<app>/`, where every host finds it. pstack's `create-verification-skill` and `maintain-verification-skill` do the work. To turn the offer off in a project, add `Verification skill: not wanted in this project.` to its `AGENTS.md` or `CLAUDE.md`.

`proof` adds nothing to the host's own setup. It uses the host's built-in tools where they exist, and installing it is the whole setup.

## Install

| Host | Install | Update |
|---|---|---|
| Claude Code | `claude plugin marketplace add Gargeya-Grey/proof`, then `claude plugin install proof@gargeya-grey` | `claude plugin marketplace update gargeya-grey`, then `claude plugin update proof@gargeya-grey` |
| Codex | `codex plugin marketplace add Gargeya-Grey/proof`, then `codex plugin add proof@gargeya-grey` | `codex plugin marketplace upgrade`, then `codex plugin add proof@gargeya-grey` |
| Grok | `grok plugin install Gargeya-Grey/proof#plugins/proof`, then confirm the trust question (or add `--trust`) | `grok plugin update` |
| Other Agent Skills hosts | `git clone https://github.com/Gargeya-Grey/proof`, then copy the files side by side (below) | `git pull`, delete the old copies, then copy again |

Start a new session after an install or an update. Grok also reads Claude Code's plugins, so with `proof` in Claude Code, Grok needs no install of its own.

**Other Agent Skills hosts** (for example OpenCode; not tested yet): `work` reads its pstack files from `../../references`, so `skills/` and `references/` must sit side by side. Copy everything in `proof/plugins/proof/skills/` into the host's skills folder. Copy `references/`, `LICENSES/`, `LICENSE` and `NOTICE.md` from `proof/plugins/proof/` into the folder above it. For OpenCode that is `~/.config/opencode/skills/` and `~/.config/opencode/references/`. Choose a folder that no other installed host reads, or the skills load twice.

Use the plugin command of your host where it has one. `npx skills add` installs single skill folders only. It leaves out the pstack files that `work` reads, so `work` then tells you to install the plugin.

## Layout

```
.claude-plugin/marketplace.json     Claude Code and Grok marketplace
.agents/plugins/marketplace.json    Codex marketplace
plugins/proof/
  .claude-plugin/plugin.json        Claude Code manifest (version source of truth)
  plugin.json                       Agent Plugins manifest (Codex reads it)
  skills/work/                      The router: this repo's own text
  skills/<5 Matt Pocock skills>/    Vendored, unchanged
  references/pstack/                Vendored, unchanged
  LICENSES/  NOTICE.md              Upstream licenses and sources
tools/vendor.py                     sync | check | refs | update
tools/release.py                    bump | check
vendor.json  vendor.lock.json       Upstream pins and file hashes
tests/                              Layout, links, router paths, byte checks, tooling
docs/maintaining.md                 Update, release, install and refresh procedures
AGENTS.md  CLAUDE.md                Instructions for agents that work on this repo
```

## Maintain

- Update from both upstreams: `python -I tools/vendor.py update`, then follow [docs/maintaining.md](docs/maintaining.md#update-from-upstream).
- Release: `python -I tools/release.py bump <major|minor|patch>`, with the bump from the [version rules](docs/maintaining.md#version-rules). Versions follow SemVer; changes are listed in [CHANGELOG.md](CHANGELOG.md).
- An agent working in this repo reads [AGENTS.md](AGENTS.md) first.

## License

Copyright (c) 2026 Gargeya Sharma. MIT license ([LICENSE](LICENSE)): use, change and share `proof` freely, and keep the copyright line and the license text in every copy.

`proof` is built on [pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan and [skills](https://github.com/mattpocock/skills) by Matt Pocock. Their files (under `plugins/proof/references/`, `plugins/proof/LICENSES/` and the five Matt Pocock skill folders) keep their own MIT licenses: see [plugins/proof/LICENSES](plugins/proof/LICENSES) and [NOTICE.md](plugins/proof/NOTICE.md).

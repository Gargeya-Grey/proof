# Changelog

All notable changes to the `proof` plugin are documented in this file.
The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The bump rules are in [docs/maintaining.md](docs/maintaining.md#version-rules).

## [Unreleased]

## [0.7.0] - 2026-11-07

### Added

- Router: a Routes row for an escape (a defect in work called done): pstack's `correct` for that class from its first report, a census before the fix, the check that should have found it, and `principle-attack-the-premise` when the class comes back after a class fix. DECISIONS.md D16.
- Router: a Routes row for a context summary: read the hub again, and every file that the summary or the task list names.
- `tests/test_plugin.py`: every vendored pstack skill needs a pointer in skill or reference text (whole names only; recorded exceptions: `blast-radius`, `recall`), the hub must name every principle, the router must enter the hub, the escape route must read `correct` and the premise principle with no negation, and the `work` description must carry the late triggers. The tests read no Markdown structure: the link test reads every line, a file with a fence marker is not a pointer source (15 vendored files are listed), and the router holds no fence. The wording tests check wording, not meaning (DECISIONS.md D16).
- `tests/router-scenarios.md`: cases 30 to 36, and a prompt that asks for the first actions in order.
- Router: three Economy rules. User calls: decide each choice inside the task and record it; ask the user only about taste, money, an irreversible step, a legal commitment, their own account, a step they kept, or a question the router or a skill it routes to asks. Refused merge: when a refusal names no specific check, review thread or approval, read unresolved review threads, required checks and required approvals first. Approvals: point the user at a prompt only when a tool result shows one waiting.
- `tests/router-scenarios.md`: cases 27 to 29 for those rules.
- Router: a Routes row to split work into units for parallel subagents: the user's own orchestration skill, else a task file (goal, units with files and acceptance checks, contracts, proving commands), workers under the worker contract, a collector, and one review of the combined diff against the task file. It replaces the swarm and Orchestrate mapping. DECISIONS.md, Skills that stay outside the plugin.
- Router: a Routes row to prove an invariant, a race, a retry, a state machine or a parser where tests reach too little: find the project's formal-verification skill by what it does; none: `create-formal-verification-skill`; one, and the checked code changed: `maintain-formal-verification-skill`.
- Vendored pstack skills `in-your-own-words`, `create-formal-verification-skill` and `maintain-formal-verification-skill` (now 45 pstack skills).
- `release.lock.json` and a release guard: `tools/release.py bump` records a digest of `plugins/proof/` (manifests included, with their version values blanked), and `release.py check` fails while the tree differs from it, so a merged change cannot reach GitHub users without a new version. DECISIONS.md D10.
- `tools/doctor.py`: reports which copy of proof Claude Code and Codex really load, from the host's own record (the latest load event in Claude Code transcripts; the plugin Codex enabled in `config.toml` and its install folder), compares each router with this repository, and says what to do. DECISIONS.md D10.
- Hooks (`hooks/hooks.json`, `hooks/proof_hook.py`) that enforce the router's context-summary row: PreCompact asks the summary for the active proof files, SessionStart after a summary adds a `proof:` notice, and file edits and shell commands are denied until the hub of this install is read again in full (the response must show the hub). Subagents are not gated, and every fault fails open. Active on Claude Code (verified), and on Codex after the user trusts the hooks (not run). DECISIONS.md rule 3 and D17.
- Router: the context-summary row names the `proof:` notice and the edit gate, and tells the agent to report once per session when no notice follows a summary.
- `tests/test_hooks.py`: 43 tests with Claude Code and Codex input shapes, run on temp folders. The gate and release hooks return before they load any module when no marker exists (4 s to 0.5 s per tool call, measured under load).
- `tests/test_release.py`: lock tests. `tests/test_doctor.py`: 8 tests on fake home folders.

### Changed

- Router: the `work` description says to load it again after a context summary and on every escape (about 100 more always-on characters).
- Router: an escape is never trivial, and in review convergence a defect in work called done takes the escape route.
- Router: the model override also covers reasoning level and speed, from the user's policy, else the Economy tier at the host's defaults.
- Router: the goal restatement (first message, PR `## Why`, final report) stays, after any line the user's rules put first.
- Router: ketchup and ketchup-video map to poteto-mode's Writing the reply; statechart (not vendored) maps to the shortest trace of each violation in plain words; sharpen is added to the not-installed list.
- Router: after a no to the verification question, every final report of the session gives the opt-out line itself (scenario case 8 dropped it twice).
- Router: a `poteto-agent` delegate gets the absolute paths of `poteto-agent.md` and the hub as its second and third files to read.
- `tests/test_plugin.py`: a `hooks/` folder in the plugin is allowed (DECISIONS.md rule 3).
- Docs: AGENTS.md, README.md and docs/maintaining.md describe the release lock and doctor. pstack `statechart` stays outside the plugin (407 files, 3.5 MB; DECISIONS.md D5).
- Upstream pstack 0.15.20 → 0.15.36 (`1b6d44f` → `c742dd6`): 47 changed, 0 added, 7 removed files.
- Upstream mattpocock/skills v1.3.1 → v1.3.2 (`24fe0ef` → `d1478fc`): 4 changed, 0 added, 0 removed files.

Upstream: pstack 0.15.36 (`c742dd6`), mattpocock/skills v1.3.2 (`d1478fc`).

## [0.6.0] - 2026-10-16

### Added

- Router: an Economy section for tasks larger than trivial, with five host-neutral rules: a checks ladder, review convergence (at most 4 outside review rounds), a worker contract for subagents, a model tier by work, and batched turns.
- `tests/router-scenarios.md`: cases 25 and 26 for the Economy section.

### Changed

- Router: the orchestration override names the Economy worker contract, and the model override falls back to the Economy model tier. DECISIONS.md D4 says the same.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.5.1] - 2026-10-12

### Added

- `tests/router-scenarios.md`: 24 router cases and 2 install cases with expected answers, run with a small model after every router change (AGENTS.md).

### Changed

- README: install steps for other Agent Skills hosts (copy `skills/` and `references/` side by side), for example OpenCode.
- docs/maintaining.md: which GitHub account pushes a release; push the branch, wait for CI to pass, then push the tag.
- Router: the review route names Claude Code's `code-review` without `--fix` as an example.
- README: other hosts copy the license files too, and delete old copies before an update.
- DECISIONS.md D4 names no model.

### Fixed

- Tests: the router path test skips the `references/...` placeholder. Linux CI failed on it; Windows accepted the `...` path part.
- README: Grok asks the user to trust a plugin before it installs it.
- DECISIONS.md D13: Claude Code has a built-in `code-review` skill that reports findings; an earlier line said it had none.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.5.0] - 2026-10-12

### Added

- Author link, `homepage` and `repository` in both manifests. The license holder is Gargeya Sharma.

### Changed

- The marketplace name is now `gargeya-grey` (was `harness-optimization`). Install with `proof@gargeya-grey`.
- README: install and update commands for `github.com/Gargeya-Grey/proof`, and a credits and license section.
- docs/maintaining.md and DECISIONS.md: local-clone instructions in place of one machine's paths.
- Router: the install guard names the repository URL.
- README credits pstack to Lauren Tan, its copyright holder.
- LICENSE holds the plain MIT text. The note on vendored files moved to the README.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.4.1] - 2026-10-12

### Added

- README and DECISIONS.md D15: how `proof` is distributed, and why `npx skills add` is not supported.

### Fixed

- Router: when the pstack files are missing (for example after `npx skills add`, which copies single skill folders), `work` tells the user to install the plugin with the host's plugin command.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.4.0] - 2026-10-12

### Added

- Router: a Verification section. For every task larger than trivial, the agent finds the project's `verify-*` skill and proves the change through it. When there is none and the task changes the app, it offers to create one with pstack's `create-verification-skill` in `.agents/skills/`, and asks the user the open decisions in `grilling` rounds. Subagents and unattended runs never ask. The user can turn the question off with one line in their instruction files.
- Router: a route to pstack's `create-verification-skill` and `maintain-verification-skill`. Before, no text pointed to them.

### Changed

- Router: the review route uses the host's own review skill that reports findings without editing (Codex `review-agent`, Grok `review`), else a self-review or one fresh reviewer. Before, it named a Claude Code `code-review` skill, which is an optional plugin and not a built-in.
- Router: pstack's `control-ui` and `control-cli` map to the project's verification skill first.
- DECISIONS.md: rule 5, host built-ins stay as they are; D13, the review replacement; D14, the verification step.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.3.0] - 2026-10-12

### Added

- `plugins/proof/LICENSE`, so a copy of the plugin folder carries the license.
- Tests: the total length of model-visible descriptions stays at or below 1200 characters; the plugin's LICENSE matches the root LICENSE.

### Fixed

- `vendor.py update` writes `vendor.json` and `CHANGELOG.md` only after the vendored files sync, and `update` and `refs` stop when `vendor.json` and the lock disagree. Before, a failed sync left a rerun reporting `up-to-date`.
- A plain `update` no longer moves a `--to` pin back to an older release. It keeps the pin until the latest release is ahead of it.
- A `--to` pin that is not a release gets the version label `<release>+<sha7>`.
- `vendor.py` reports a clear error when the download fails and `gh` is missing.
- Router: the review step that `tdd` names now follows the Review route, so Claude Code uses its `code-review` skill.
- Router: resuming work goes to pstack's Session pickup playbook; pausing or handing off goes to its Pause safely playbook, with the `handoff` note.
- Router: the Investigation route names its playbook file, and the Path rule says a `skills/` path is at the plugin root, never under `references/`.
- Maintainer docs: the exit codes of `update`, a reachable done condition for the Map step, and the full file list for a new model-visible skill.
- Manifest and marketplace descriptions name Grok and other Agent Skills hosts.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.2.0] - 2026-10-12

### Added

- Routes table in the `work` router: debugging, research, review, plan testing, module design, agent writing and hand-off each have a fixed first stop.
- `tools/vendor.py update`: one command moves both upstream pins to their latest releases and reports what needs a router change.
- `tools/release.py`: SemVer bump and release checks.
- Maintainer instructions for agents: `AGENTS.md`, `CLAUDE.md` and `docs/maintaining.md`.
- CI workflow that runs the checks on Linux and Windows.
- MIT license for this repository's own files.

### Changed

- Router wording names no owner-specific files, so the plugin works for other users.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

## [0.1.0] - 2026-10-12

### Added

- First build: the `work` router, five Matt Pocock skills (`grilling`, `tdd`, `codebase-design`, `writing-for-agents`, `handoff`) and the pstack text as on-demand references.

Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`).

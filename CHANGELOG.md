# Changelog

All notable changes to the `proof` plugin are documented in this file.
The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The bump rules are in [docs/maintaining.md](docs/maintaining.md#version-rules).

## [Unreleased]

### Added

- Router: an Economy section for tasks larger than trivial, with five host-neutral rules: a checks ladder, review convergence (at most 4 outside review rounds), a worker contract for subagents, a model tier by work, and batched turns.
- `tests/router-scenarios.md`: cases 25 and 26 for the Economy section.

### Changed

- Router: the orchestration override names the Economy worker contract, and the model override falls back to the Economy model tier. DECISIONS.md D4 says the same.

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

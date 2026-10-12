# proof plugin repository

This repository builds `proof`: one plugin that gives Claude Code, Codex, Grok and other Agent Skills hosts the same verification-first workflow, from unchanged pstack and Matt Pocock text plus one router skill. [DECISIONS.md](DECISIONS.md) holds the reasons; read it before you change the layout, the router or what is vendored.

## Tasks

- **Update** from upstream (pstack, Matt Pocock skills): follow [docs/maintaining.md](docs/maintaining.md#update-from-upstream).
- **Release** a version: follow [docs/maintaining.md](docs/maintaining.md#release).
- **Install or refresh** the plugin on a host: see [docs/maintaining.md](docs/maintaining.md#install-and-refresh).
- **Change the router** (`plugins/proof/skills/work/SKILL.md`): load the `writing-for-agents` skill first; every pstack name the vendored text uses must stay reachable.

## Rules

- Vendored files change only through `tools/vendor.py`: `plugins/proof/references/`, `plugins/proof/LICENSES/`, and the skill folders `grilling`, `tdd`, `codebase-design`, `writing-for-agents`, `handoff`. Host-specific wording goes in the router or in `plugins/proof/skills/work/agents/openai.yaml`.
- Every change to the plugin adds a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
- Commit, tag and push only when the owner asks.
- Scratch files go in `_scratch/` (git ignores it).
- Verification skill: not wanted in this project. The checks below are this repository's proof.

## Checks

The work is done when all of these pass:

```
python -I tools/vendor.py check
python -I -m unittest discover -s tests
python -I tools/release.py check
claude plugin validate plugins/proof
```

CI (`.github/workflows/check.yml`) runs the first three. The last one needs the Claude Code CLI, so run it locally.

# Maintaining proof

Three procedures: update from upstream, release, install and refresh. Each step ends with the condition that makes it done.

## Update from upstream

The two parent projects are pinned by commit in `vendor.json`, and `update` moves each pin only to that project's latest release:

| Source | Repository | A release is |
|---|---|---|
| pstack | `cursor/plugins`, folder `pstack` | The latest commit that changed `pstack/plugin.json` (Cursor bumps the version there; the repo has no tags). |
| Matt Pocock's skills | `mattpocock/skills` | The latest GitHub release (not a prerelease). |

To take one exact commit instead, run `update --source <name> --to <sha>`. A later plain `update` keeps that pin until the project's latest release is ahead of it (the report says `kept pin`).

1. **Fetch.** Run `python -I tools/vendor.py update`. For one source, add `--source pstack` or `--source mattpocock`. To preview without writing, add `--dry-run`.
   Done when the last line is a `RESULT:` line:

   | Last line | Exit code | Next |
   |---|---|---|
   | `RESULT: up-to-date` | 0 | Stop. There is nothing to release. |
   | `RESULT: updated` | 0 | Step 2. |
   | `RESULT: updated, action needed` | 3 | Step 2. The report lists `UNMAPPED` names for step 3. |
   | `error: ...` (no `RESULT:` line) | 1 | Fix the cause the error names. Run `python -I tools/vendor.py check`; when it fails, run `python -I tools/vendor.py sync`. Then run step 1 again. |
2. **Read the rule changes.** The report lists the changed rule files (every `SKILL.md`, the poteto-mode playbooks, the agent briefs). Their diff is in `_scratch/vendor-update.patch`. Read every hunk of every listed file and mark each added or changed instruction that:
   - names a skill, tool, model, folder or command the router does not cover, or
   - conflicts with the router's Authority or Overrides: commits, pushes, PRs, actions outside the machine, model choice, Cursor-only tools.
   Done when every hunk of every listed file is read and each marked instruction is written down.
3. **Map.** Load the `writing-for-agents` skill first. For each marked instruction and each `UNMAPPED` name in the report, add or change one row in the router (`plugins/proof/skills/work/SKILL.md`: Routes, Overrides or Host map). To ship a pstack skill as a reference instead of a row, copy one `"type": "dir"` rule for `pstack/skills/<name>` in `vendor.json`, set its `from` and `to`, and run `python -I tools/vendor.py sync`.
   Done when `python -I tools/vendor.py refs` ends with `0 UNMAPPED` and every marked instruction has a row.

   A new model-visible skill (for example another Matt Pocock skill) is a design change, not a step of this procedure: it adds always-on tokens in every session of every user. Ask the owner first. Its name must not match a built-in skill of Claude Code, Codex or Grok (DECISIONS.md, rule 5). It needs a `vendor.json` rule and a `managed_roots` entry, the same folder in `ALLOWED_ROOTS` (`tools/vendor.py`), a `-text` line in `.gitattributes`, the folder in the vendored list in `AGENTS.md`, the name in `ALL_SKILLS` and `MODEL_VISIBLE` (`tests/test_plugin.py`), a row in the `README.md` and `DECISIONS.md` D2 tables, and a `minor` bump. `test_04_total_description_budget` fails when the descriptions together pass 1200 characters.
4. **Log.** `update` already added the upstream line under `## [Unreleased]` in `CHANGELOG.md`. Add one line for each router change.
5. **Check.** Run the checks in [AGENTS.md](../AGENTS.md#checks).
   Done when all pass.
6. **Release** with a `minor` bump (next section), then **refresh** the hosts (last section).

## Release

### Version rules

`proof` uses Semantic Versioning. The version lives in `plugins/proof/.claude-plugin/plugin.json`; `tools/release.py` copies it into `plugins/proof/plugin.json`.

| Bump | When |
|---|---|
| major | A skill is removed or renamed, the router's Authority order changes, or a host loses support. |
| minor | An upstream update, a new skill, a new route or override. |
| patch | A wording fix that keeps behaviour; a fix for a broken or unsupported install; tooling, tests or docs only. |

While the version is `0.x`, a breaking change bumps minor instead of major.

The version matters for people who install from GitHub: Claude Code and Codex deliver a change to them only when the version changes. From a local clone, Claude Code and Grok load the plugin in place and `codex plugin add` copies it again, so local changes need no bump.

### Steps

1. Check that `## [Unreleased]` in `CHANGELOG.md` lists every change since the last release.
2. Run `python -I tools/release.py bump <major|minor|patch>` with the bump from the table.
   Done when both manifests show the new version and `CHANGELOG.md` has a `## [x.y.z] - date` section with an `Upstream:` line.
3. Run the checks in [AGENTS.md](../AGENTS.md#checks).
4. Only when the owner asks: commit (`release: proof x.y.z`), run `claude plugin tag plugins/proof` (it creates the tag `proof--vx.y.z` after it checks the manifests), then push the branch and the tag.

## Install and refresh

Users install from GitHub with the commands in [README.md](../README.md#install).

To test changes before a release, install from your local clone. The marketplace is then the clone folder.

| Host | Install once | After a change |
|---|---|---|
| Claude Code | `claude plugin marketplace add <clone path>`, then `claude plugin install proof@gargeya-grey` | Loads in place. Start a new session or run `/reload-plugins`. |
| Codex | `codex plugin marketplace add <clone path>`, then `codex plugin add proof@gargeya-grey` | Codex keeps a copy. Run `codex plugin add proof@gargeya-grey` again, then start a new session. |
| Grok | Nothing. Grok reads Claude Code's plugin settings (`[compat.claude]`, on by default), so it loads `proof` in place. | Start a new session. |
| Other Agent Skills hosts | Add `<clone path>/plugins/proof/skills` to the host's skill paths. Keep it inside the clone: the router reads `../../references`. | Start a new session. |

One marketplace name can point to one source at a time. Remove a GitHub install of `gargeya-grey` before you add the local clone, and the reverse.

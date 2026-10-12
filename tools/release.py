#!/usr/bin/env python3
"""Cut a SemVer release of the proof plugin. Never runs git.

  python -I tools/release.py bump {major|minor|patch} [--date YYYY-MM-DD] [--dry-run]
  python -I tools/release.py check

Version source of truth: plugins/proof/.claude-plugin/plugin.json ("version").
bump writes the new version into that file and into plugins/proof/plugin.json, and moves the
`## [Unreleased]` body of CHANGELOG.md (Keep a Changelog 1.1.0) into `## [x.y.z] - date`, followed
by the line `Upstream: ...` built from vendor.json. check verifies that all of this agrees.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CLAUDE_MANIFEST = "plugins/proof/.claude-plugin/plugin.json"
CODEX_MANIFEST = "plugins/proof/plugin.json"
CHANGELOG = "CHANGELOG.md"
VENDOR_JSON = "vendor.json"

# Official SemVer 2.0.0 regular expression (https://semver.org).
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$")
_VERSION_VALUE_RE = re.compile(r'("version"\s*:\s*")([^"\\]*)(")')
_UNRELEASED_RE = re.compile(r"(?m)^## \[Unreleased\][ \t]*$")
_NEXT_BLOCK_RE = re.compile(r"(?m)^(## |\[[^\]\n]+\]: )")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReleaseError(Exception):
    pass


def _read(root, rel):
    p = Path(root) / rel
    if not p.is_file():
        raise ReleaseError(f"missing file: {rel}")
    return p.read_bytes().decode("utf-8")


def _write(root, rel, text):
    (Path(root) / rel).write_bytes(text.encode("utf-8"))


def read_version(root, rel):
    try:
        v = json.loads(_read(root, rel)).get("version")
    except ValueError as exc:
        raise ReleaseError(f"{rel}: not valid JSON ({exc})")
    if not isinstance(v, str):
        raise ReleaseError(f"{rel}: no string 'version' key")
    return v


def set_version_text(text, new_version, rel="manifest"):
    """Replace the value of the one "version" key and change nothing else."""
    matches = _VERSION_VALUE_RE.findall(text)
    if len(matches) != 1:
        raise ReleaseError(f"{rel}: expected exactly one \"version\" key, found {len(matches)}")
    return _VERSION_VALUE_RE.sub(lambda m: m.group(1) + new_version + m.group(3), text, count=1)


def next_version(current, part):
    m = SEMVER_RE.match(current)
    if not m:
        raise ReleaseError(f"current version is not valid SemVer: {current!r}")
    if m.group(4) or m.group(5):
        raise ReleaseError(f"current version {current!r} has a pre-release or build part; set it by hand")
    major, minor, patch = (int(m.group(i)) for i in (1, 2, 3))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError(f"unknown bump part: {part!r}")


def upstream_line(vendor_cfg):
    parts = []
    for name, s in vendor_cfg["sources"].items():
        parts.append(f"{s.get('label', name)} {s['version']} (`{s['sha'][:7]}`)")
    return "Upstream: " + ", ".join(parts) + "."


def read_vendor(root):
    try:
        return json.loads(_read(root, VENDOR_JSON))
    except ValueError as exc:
        raise ReleaseError(f"{VENDOR_JSON}: not valid JSON ({exc})")


def split_unreleased(text):
    """Return (before, body, after) around `## [Unreleased]`: before ends with the heading line,
    body is the text up to the next `## ` heading or link-reference block, after is the rest."""
    m = _UNRELEASED_RE.search(text)
    if not m:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' heading")
    nxt = _NEXT_BLOCK_RE.search(text, m.end())
    end = nxt.start() if nxt else len(text)
    return text[:m.end()], text[m.end():end], text[end:]


def has_entries(body):
    return re.search(r"(?m)^\s*[-*+]\s+\S", body) is not None


def release_changelog(text, version, date):
    """Return (new_text, moved_body). Raises when Unreleased has no entries."""
    nl = "\r\n" if "\r\n" in text else "\n"
    t = text.replace("\r\n", "\n")
    before, body, after = split_unreleased(t)
    if not has_entries(body):
        raise ReleaseError("## [Unreleased] has no entries; nothing to release")
    heading = f"## [{version}] - {date}"
    if re.search(rf"(?m)^## \[{re.escape(version)}\]", t):
        raise ReleaseError(f"CHANGELOG.md already has a section for {version}")
    new = (before + "\n\n" + heading + "\n\n" + body.strip("\n") + "\n\n@@UPSTREAM@@\n"
           + ("\n" if after else "") + after)
    return new.replace("\n", nl) if nl != "\n" else new, body.strip("\n")


def finish_changelog(text, upstream):
    return text.replace("@@UPSTREAM@@", upstream, 1)


def plan_bump(root, part, date):
    """Compute every change of a bump without writing. Returns a dict."""
    old = read_version(root, CLAUDE_MANIFEST)
    other = read_version(root, CODEX_MANIFEST)
    if old != other:
        raise ReleaseError(f"manifests disagree: {CLAUDE_MANIFEST} {old} vs {CODEX_MANIFEST} {other}")
    new = next_version(old, part)
    if not _DATE_RE.match(date):
        raise ReleaseError(f"--date must be YYYY-MM-DD, got {date!r}")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ReleaseError(f"--date is not a real date: {date}")
    up = upstream_line(read_vendor(root))
    changelog, moved = release_changelog(_read(root, CHANGELOG), new, date)
    return {
        "old": old, "new": new, "date": date, "upstream": up, "moved": moved,
        "files": {
            CLAUDE_MANIFEST: set_version_text(_read(root, CLAUDE_MANIFEST), new, CLAUDE_MANIFEST),
            CODEX_MANIFEST: set_version_text(_read(root, CODEX_MANIFEST), new, CODEX_MANIFEST),
            CHANGELOG: finish_changelog(changelog, up),
        },
    }


def cmd_bump(root, part, date, dry_run):
    plan = plan_bump(root, part, date)
    bullets = sum(1 for l in plan["moved"].split("\n") if re.match(r"\s*[-*+]\s+\S", l))
    print(f"{'planned (dry run, nothing written)' if dry_run else 'bump'}: {plan['old']} -> {plan['new']} ({part})")
    print(f"  {CLAUDE_MANIFEST}: version {plan['old']} -> {plan['new']}")
    print(f"  {CODEX_MANIFEST}: version {plan['old']} -> {plan['new']}")
    print(f"  {CHANGELOG}: move {bullets} Unreleased entr{'y' if bullets == 1 else 'ies'} "
          f"into '## [{plan['new']}] - {plan['date']}'; leave an empty '## [Unreleased]'")
    print(f"  {CHANGELOG}: append '{plan['upstream']}'")
    if dry_run:
        return 0
    for rel, text in plan["files"].items():
        _write(root, rel, text)
    print("next steps (release.py runs none of them):")
    print("  1. Review the changes, then run: python -I tools/release.py check")
    print("  2. When the owner asks: commit the release.")
    print("  3. Tag the release: claude plugin tag plugins/proof")
    return 0


def pending_sources(root, text=None):
    """Names of sources whose update is listed under `## [Unreleased]` ('Upstream <label> ... →')
    and therefore not yet in a released Upstream line."""
    try:
        cfg = read_vendor(root)
        t = (text if text is not None else _read(root, CHANGELOG)).replace("\r\n", "\n")
        body = split_unreleased(t)[1]
    except (ReleaseError, KeyError):
        return []
    return [name for name, s in cfg["sources"].items()
            if re.search(rf"(?m)^\s*[-*+]\s+Upstream {re.escape(s.get('label', name))} .*(?:→|->)", body)]


def check_problems(root):
    """Return a list of failure strings; empty when the release state is consistent."""
    problems = []
    versions = {}
    for rel in (CLAUDE_MANIFEST, CODEX_MANIFEST):
        try:
            versions[rel] = read_version(root, rel)
        except ReleaseError as exc:
            problems.append(str(exc))
    if len(set(versions.values())) > 1:
        problems.append("manifests disagree: " + ", ".join(f"{k} {v}" for k, v in versions.items()))
    if CLAUDE_MANIFEST not in versions:
        return problems
    version = versions[CLAUDE_MANIFEST]
    if not SEMVER_RE.match(version):
        problems.append(f"version is not valid SemVer 2.0.0: {version!r}")
        return problems
    try:
        text = _read(root, CHANGELOG).replace("\r\n", "\n")
    except ReleaseError as exc:
        problems.append(str(exc))
        return problems
    m = re.search(rf"(?m)^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})[ \t]*$", text)
    if not m:
        problems.append(f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' section")
        return problems
    nxt = _NEXT_BLOCK_RE.search(text, m.end())
    section = text[m.end():nxt.start() if nxt else len(text)]
    try:
        cfg = read_vendor(root)
        want = upstream_line(cfg)
    except (ReleaseError, KeyError) as exc:
        problems.append(f"cannot build the Upstream line from vendor.json: {exc}")
        return problems
    pending = set(pending_sources(root, text))
    lines = [l for l in section.split("\n") if l.startswith("Upstream:")]
    if not lines:
        problems.append(f"CHANGELOG.md section [{version}] has no 'Upstream:' line (want: {want})")
    elif not pending:
        if lines[0] != want:
            problems.append(f"CHANGELOG.md section [{version}] Upstream line differs from vendor.json:\n"
                            f"    have: {lines[0]}\n    want: {want}")
    else:
        # A source with an unreleased update is allowed to differ; compare the others one by one.
        for name, s in cfg["sources"].items():
            if name in pending:
                continue
            seg = f"{s.get('label', name)} {s['version']} (`{s['sha'][:7]}`)"
            if seg not in lines[0]:
                problems.append(f"CHANGELOG.md section [{version}] Upstream line lacks '{seg}' from vendor.json")
    return problems


def cmd_check(root):
    problems = check_problems(root)
    for p in problems:
        print("FAIL: " + p)
    try:
        cfg = read_vendor(root)
        for name in pending_sources(root):
            print(f"pending release: {cfg['sources'][name].get('label', name)}")
    except ReleaseError:
        pass
    if problems:
        return 1
    print(f"release check: ok (version {read_version(root, CLAUDE_MANIFEST)})")
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="release.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=str(ROOT), help="repository root (default: this repository; for tests)")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bump")
    b.add_argument("part", choices=["major", "minor", "patch"])
    b.add_argument("--date", default=None, help="release date YYYY-MM-DD (default: today)")
    b.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    sub.add_parser("check")
    args = p.parse_args(argv[1:])
    try:
        if args.cmd == "check":
            return cmd_check(Path(args.root))
        return cmd_bump(Path(args.root), args.part, args.date or datetime.date.today().isoformat(), args.dry_run)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

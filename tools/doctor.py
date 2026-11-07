#!/usr/bin/env python3
"""Report which copy of proof each host on this machine really loads. Never runs git; reads only.

  python -I tools/doctor.py [--home DIR] [--repo DIR]

A cache folder is not proof of what a host loads (DECISIONS.md D10: on 7 Nov a 0.6.0 cache was
taken for the live copy, while Claude Code loaded the repository in place). So each line comes from
the host's own record:

- Claude Code: the newest "Base directory for this skill: ...work" line in ~/.claude/projects
  transcripts, the folder the host printed when it loaded the router.
- Codex: the newest version folder under ~/.codex/plugins/cache/*/proof/, the copy Codex installs
  and runs (Codex copies a plugin on `codex plugin add`).

Each line compares that copy's router with this repository's router (same, or differs) and ends
with what to do. Exit code 1 when a host loads a copy whose router differs from the repository's.
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTER_REL = Path("skills") / "work" / "SKILL.md"
BASE_RE = re.compile(r"Base directory for this skill: ((?:[^\"\\]|\\\\)+?[\\/]+work)\b")
SCAN_FILES = 200  # newest transcripts read; enough to find a recent load, cheap to run


def router_digest(plugin_root):
    p = Path(plugin_root) / ROUTER_REL
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _clean(path_text):
    """A JSON-escaped Windows path from a transcript line, as a real path."""
    s = path_text.replace("\\\\", "\\")
    s = re.sub(r"[\\/]+", "/", s)
    return s


def claude_loaded_root(home):
    """(plugin root, transcript) of the newest proof router load that Claude Code recorded, or None."""
    projects = Path(home) / ".claude" / "projects"
    if not projects.is_dir():
        return None
    files = []
    for p in projects.glob("*/*.jsonl"):
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            continue
    for _, p in sorted(files, reverse=True)[:SCAN_FILES]:
        found = None
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "Base directory for this skill" not in line:
                        continue
                    for m in BASE_RE.finditer(line):
                        path = _clean(m.group(1))
                        if "proof" in path:
                            found = path
        except OSError:
            continue
        if found:
            root = Path(found).parent.parent  # .../skills/work -> plugin root
            return root, p
    return None


def _version_key(name):
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[.+-]", name))


def codex_installed_root(home):
    cache = Path(home) / ".codex" / "plugins" / "cache"
    if not cache.is_dir():
        return None
    roots = [p for p in cache.glob("*/proof/*") if (p / ROUTER_REL).is_file()]
    if not roots:
        return None
    return max(roots, key=lambda p: _version_key(p.name))


def report(home, repo):
    """Return (lines, exit code)."""
    want = router_digest(Path(repo) / "plugins" / "proof")
    if want is None:
        return [f"error: no router at {Path(repo) / 'plugins' / 'proof' / ROUTER_REL}"], 1
    lines, code = [], 0

    claude = claude_loaded_root(home)
    if claude is None:
        lines.append("claude: no proof router load found in the newest transcripts (not loaded yet, or not installed)")
    else:
        root, transcript = claude
        have = router_digest(root)
        if have == want:
            lines.append(f"claude: loads {root}; router same as this repository (from {transcript.name})")
        elif have is None:
            lines.append(f"claude: last load was {root}, which no longer exists; start a new session")
        else:
            code = 1
            fix = ("it is a local clone that loads in place: merge the change into that checkout"
                   if (root.parent.parent / ".git").exists() else
                   "run `claude plugin update proof@gargeya-grey` (a GitHub install updates only on a new version)")
            lines.append(f"claude: loads {root}; router DIFFERS from this repository; {fix}, then start a new session")

    codex = codex_installed_root(home)
    if codex is None:
        lines.append("codex: no installed proof copy found")
    elif router_digest(codex) == want:
        lines.append(f"codex: runs {codex}; router same as this repository")
    else:
        code = 1
        lines.append(f"codex: runs {codex}; router DIFFERS from this repository. "
                     "Run `codex plugin add proof@gargeya-grey`, then start a new session")

    lines.append("grok: reads Claude Code's plugin settings, so it loads the copy on the claude line (DECISIONS.md D12)")
    return lines, code


def main(argv):
    p = argparse.ArgumentParser(prog="doctor.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--home", default=os.path.expanduser("~"), help="home folder to inspect (for tests)")
    p.add_argument("--repo", default=str(ROOT), help="repository root (default: this repository)")
    args = p.parse_args(argv[1:])
    lines, code = report(args.home, args.repo)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Report which copy of proof each host on this machine really loads. Never runs git; reads only.

  python -I tools/doctor.py [--home DIR] [--repo DIR]

A cache folder is not proof of what a host loads (DECISIONS.md D10: on 7 Nov a 0.6.0 cache was
taken for the live copy, while Claude Code loaded the repository in place). So each line comes from
the host's own record:

- Claude Code: the latest "Base directory for this skill: ...work" load event (by its timestamp) in
  ~/.claude/projects transcripts, the folder the host printed when it loaded the router.
- Codex: the proof plugin enabled in ~/.codex/config.toml, and its newest version folder under
  ~/.codex/plugins/cache/<marketplace>/proof/, the copy Codex installs and runs.

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


TIME_RE = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')


def _clean(path_text):
    """A JSON-escaped path from a transcript line, as a real path. A UNC prefix (\\\\server\\share)
    keeps its two leading separators; every other run of separators becomes one slash."""
    s = path_text.replace("\\\\", "\\")
    unc = re.match(r"^[\\/]{2}(?=[^\\/])", s) is not None
    s = re.sub(r"[\\/]+", "/", s)
    return "/" + s if unc else s


def claude_loaded_root(home):
    """(plugin root, transcript) of the newest proof router load that Claude Code recorded, or None.

    Newest means the latest load event (its line's timestamp), not the latest-written transcript: an
    old session that is still running writes its transcript last but loaded its copy long ago."""
    projects = Path(home) / ".claude" / "projects"
    if not projects.is_dir():
        return None
    files = []
    for p in projects.glob("*/*.jsonl"):
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            continue
    best = None  # (timestamp text, file mtime, path, transcript)
    for mtime, p in sorted(files, reverse=True)[:SCAN_FILES]:
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "Base directory for this skill" not in line:
                        continue
                    stamp = TIME_RE.search(line)
                    for m in BASE_RE.finditer(line):
                        path = _clean(m.group(1))
                        if "proof" in path:
                            # ISO 8601 UTC stamps sort as text; a line without one sorts first.
                            key = (stamp.group(1) if stamp else "", mtime)
                            if best is None or key >= best[0]:
                                best = (key, path, p)
        except OSError:
            continue
    if best is None:
        return None
    return Path(best[1]).parent.parent, best[2]  # .../skills/work -> plugin root


def _version_key(name):
    """Sort key for a version folder name. Numbers compare as numbers and sort above words, so
    `0.10.0` > `0.9.0` and a `local` folder never makes the comparison fail."""
    return tuple((1, int(x), "") if x.isdigit() else (0, 0, x) for x in re.split(r"[.+-]", name))


def codex_enabled(home):
    """Marketplace names whose proof plugin Codex has enabled, from ~/.codex/config.toml
    ([plugins."proof@<marketplace>"] enabled = true). None when the file cannot be read."""
    path = Path(home) / ".codex" / "config.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import tomllib  # Python 3.11+
        plugins = tomllib.loads(text).get("plugins", {})
        return {k.split("@", 1)[1] for k, v in plugins.items()
                if k.startswith("proof@") and isinstance(v, dict) and v.get("enabled") is True}
    except ImportError:
        found = set()
        for m in re.finditer(r'(?ms)^\[plugins\."proof@([^"]+)"\]\s*$(.*?)(?=^\[|\Z)', text):
            if re.search(r"(?m)^\s*enabled\s*=\s*true\s*$", m.group(2)):
                found.add(m.group(1))
        return found
    except ValueError:
        return None


def codex_installed_root(home):
    """(copy, note) for the proof copy Codex runs, or None. Codex records which plugin is enabled in
    config.toml and keeps the installed files in cache/<marketplace>/proof/<version>/. When one
    marketplace holds several version folders, the newest is taken, and the note says so."""
    cache = Path(home) / ".codex" / "plugins" / "cache"
    if not cache.is_dir():
        return None
    enabled = codex_enabled(home)
    roots = [p for p in cache.glob("*/proof/*") if (p / ROUTER_REL).is_file()]
    if enabled is not None:
        roots = [p for p in roots if p.parent.parent.name in enabled]
    if not roots:
        return None
    best = max(roots, key=lambda p: (_version_key(p.name), p.parent.parent.name))
    same = [p for p in roots if p.parent == best.parent]
    notes = []
    if enabled is None:
        notes.append("config.toml not read, so the enabled state is not checked")
    if len(same) > 1:
        notes.append(f"{len(same)} version folders; the newest is assumed to run")
    return best, "; ".join(notes)


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

    found = codex_installed_root(home)
    if found is None:
        lines.append("codex: no installed and enabled proof copy found")
    else:
        codex, note = found
        note = f" ({note})" if note else ""
        if router_digest(codex) == want:
            lines.append(f"codex: runs {codex}; router same as this repository{note}")
        else:
            code = 1
            lines.append(f"codex: runs {codex}; router DIFFERS from this repository{note}. "
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

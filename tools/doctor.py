#!/usr/bin/env python3
"""Report which copy of proof each host on this machine really loads. Never runs git; reads only.

  python -I tools/doctor.py [--home DIR] [--repo DIR]

A cache folder is not proof of what a host loads (DECISIONS.md D10: on 7 Nov a 0.6.0 cache was
taken for the live copy, while Claude Code loaded the repository in place). So each line comes from
the host's own record:

- Claude Code: the latest "Base directory for this skill: ...work" load event (by its timestamp) in
  ~/.claude/projects transcripts, the folder the host printed when it loaded the router.
- Codex: every installed copy under <codex home>/plugins/cache/<marketplace>/proof/<version>/
  (`local` for a local plugin), narrowed to the marketplace that config.toml enables. Codex does
  not record which version folder runs, so each copy is compared.

The host folders are CLAUDE_CONFIG_DIR and CODEX_HOME when set, as the hosts read them, else
~/.claude and ~/.codex. A user-level disable is noted, not trusted: a project's settings can
enable a plugin.

Each line compares that copy's router with this repository's router (same, or differs) and ends
with what to do. Exit code 1 when a host loads a copy whose router differs from the repository's.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTER_REL = Path("skills") / "work" / "SKILL.md"
LOAD_PREFIX = "Base directory for this skill: "
SCAN_FILES = 200  # newest transcripts read; enough to find a recent load, cheap to run


def router_digest(plugin_root):
    p = Path(plugin_root) / ROUTER_REL
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _clean(path_text, escaped=True):
    """A path from a transcript line, as a real path (escaped: still JSON-escaped). A UNC prefix
    (\\\\server\\share) keeps its two leading separators; every other run of separators becomes one slash."""
    s = path_text.replace("\\\\", "\\") if escaped else path_text
    unc = re.match(r"^[\\/]{2}(?=[^\\/])", s) is not None
    s = re.sub(r"[\\/]+", "/", s)
    return "/" + s if unc else s


def _skill_loads(line):
    """(router path, timestamp) for each real skill load a transcript line records: a user entry
    whose text block starts with the load line. A quote of it in a tool call or result is not a load."""
    if LOAD_PREFIX not in line:
        return []
    try:
        entry = json.loads(line)
    except ValueError:
        return []
    if not isinstance(entry, dict) or entry.get("type") != "user":
        return []
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    found = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text") or ""
            if text.startswith(LOAD_PREFIX):
                path = text[len(LOAD_PREFIX):].splitlines()[0].strip() if len(text) > len(LOAD_PREFIX) else ""
                if re.search(r"[\\/]work$", path):
                    found.append((_clean(path, escaped=False), entry.get("timestamp") or ""))
    return found


def claude_enabled(claude_dir):
    """True or False from enabledPlugins in ~/.claude/settings.json for the proof@<marketplace> keys,
    None when the file cannot be read or names no proof plugin."""
    try:
        data = json.loads((Path(claude_dir) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return None
    values = [v for k, v in plugins.items() if str(k).startswith("proof@")]
    if not values:
        return None
    return any(v is True for v in values)


def claude_loaded_root(claude_dir):
    """(plugin root, transcript, timestamp) of the newest proof router load that Claude Code
    recorded, or None. Newest means the latest load event (its timestamp), not the latest-written
    transcript: an old session that is still running writes its transcript last but loaded long ago."""
    projects = Path(claude_dir) / "projects"
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
                    for path, stamp in _skill_loads(line):
                        if "proof" in path:
                            # ISO 8601 UTC stamps sort as text; a load without one sorts first.
                            key = (stamp, mtime)
                            if best is None or key >= best[0]:
                                best = (key, path, p)
        except OSError:
            continue
    if best is None:
        return None
    return Path(best[1]).parent.parent, best[2], best[0][0]  # .../skills/work -> plugin root


SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def _version_key(name):
    """Sort key for a version folder name, by SemVer 2.0.0 precedence: `0.10.0` > `0.9.0`, and a
    release > its prereleases (`0.7.0` > `0.7.0-rc.1`). A name that is not SemVer (`local`) sorts
    below every version, so the comparison never fails."""
    m = SEMVER_RE.match(name)
    if not m:
        return (0, name)
    pre = m.group(4)
    if pre is None:
        tail = (1,)
    else:
        tail = (0,) + tuple((0, int(x), "") if x.isdigit() else (1, 0, x) for x in pre.split("."))
    return (1, int(m.group(1)), int(m.group(2)), int(m.group(3))) + tail


def codex_enabled(codex_dir):
    """Marketplace names whose proof plugin Codex has enabled, from ~/.codex/config.toml
    ([plugins."proof@<marketplace>"] enabled = true). None when the file cannot be read."""
    path = Path(codex_dir) / "config.toml"
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


def codex_copies(codex_dir):
    """(copies, notes) for the proof copies Codex may run. Codex keeps installed files in
    cache/<marketplace>/proof/<version>/ (`local` for a local plugin) and records the enabled plugin
    in config.toml, but not which version folder runs. So every candidate is returned, and the
    caller compares each one; nothing is guessed from folder names."""
    cache = Path(codex_dir) / "plugins" / "cache"
    if not cache.is_dir():
        return [], []
    roots = sorted((p for p in cache.glob("*/proof/*") if (p / ROUTER_REL).is_file()),
                   key=lambda p: (p.parent.parent.name, _version_key(p.name)), reverse=True)
    enabled = codex_enabled(codex_dir)
    notes = []
    if enabled is None:
        notes.append("config.toml not read, so the enabled state is not checked")
    elif enabled:
        chosen = [p for p in roots if p.parent.parent.name in enabled]
        if chosen:
            roots = chosen
    elif roots:
        notes.append("the user config.toml does not enable proof; a project's .codex/config.toml may (not checked)")
    return roots, notes


def host_dirs(home=None):
    """(Claude Code folder, Codex folder). With a home folder (tests, --home): its .claude and
    .codex. Without one: CLAUDE_CONFIG_DIR and CODEX_HOME when set, as the hosts themselves read
    them, else ~/.claude and ~/.codex."""
    if home is not None:
        return Path(home) / ".claude", Path(home) / ".codex"
    user = Path(os.path.expanduser("~"))
    claude = os.environ.get("CLAUDE_CONFIG_DIR") or str(user / ".claude")
    codex = os.environ.get("CODEX_HOME") or str(user / ".codex")
    return Path(claude), Path(codex)


def report(home, repo):
    """Return (lines, exit code). home=None reads the folders the hosts use (host_dirs)."""
    want = router_digest(Path(repo) / "plugins" / "proof")
    if want is None:
        return [f"error: no router at {Path(repo) / 'plugins' / 'proof' / ROUTER_REL}"], 1
    claude_dir, codex_dir = host_dirs(home)
    lines, code = [], 0

    claude = claude_loaded_root(claude_dir)
    enabled = claude_enabled(claude_dir)
    if claude is None:
        state = " (proof is not enabled in its settings.json)" if enabled is False else ""
        lines.append("claude: no proof router load found in the newest transcripts "
                     f"(not loaded yet, or not installed){state}")
    else:
        root, transcript, stamp = claude
        seen = f"last load seen {stamp or 'at an unknown time'} in {transcript.name}"
        if enabled is False:
            seen += f"; {claude_dir / 'settings.json'} disables proof, so this may be history unless a project's settings enable it"
        elif enabled is None:
            seen += f"; {claude_dir / 'settings.json'} names no proof plugin, so this may be history"
        have = router_digest(root)
        if have == want:
            lines.append(f"claude: loads {root}; router same as this repository ({seen})")
        elif have is None:
            lines.append(f"claude: last load was {root}, which no longer exists ({seen}); start a new session")
        else:
            code = 1
            fix = ("it is a local clone that loads in place: merge the change into that checkout"
                   if (root.parent.parent / ".git").exists() else
                   "run `claude plugin update proof@gargeya-grey` (a GitHub install updates only on a new version)")
            lines.append(f"claude: loads {root}; router DIFFERS from this repository ({seen}); {fix}, then start a new session")

    copies, notes = codex_copies(codex_dir)
    note = f" ({'; '.join(notes)})" if notes else ""
    if not copies:
        lines.append(f"codex: no installed proof copy found{note}")
    else:
        differ = [c for c in copies if router_digest(c) != want]
        if len(copies) > 1:
            notes.append(f"{len(copies)} copies; Codex does not record which one runs, so each is compared")
            note = f" ({'; '.join(notes)})"
        if not differ:
            where = copies[0] if len(copies) == 1 else ", ".join(str(c) for c in copies)
            lines.append(f"codex: runs {where}; router same as this repository{note}")
        else:
            code = 1
            lines.append(f"codex: {', '.join(str(c) for c in differ)}: router DIFFERS from this repository{note}. "
                         "Run `codex plugin add proof@gargeya-grey`, then start a new session")

    lines.append("grok: reads Claude Code's plugin settings, so it loads the copy on the claude line (DECISIONS.md D12)")
    return lines, code


def main(argv):
    p = argparse.ArgumentParser(prog="doctor.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--home", default=None,
                   help="home folder to inspect (for tests); default: the folders the hosts use, "
                        "with CLAUDE_CONFIG_DIR and CODEX_HOME")
    p.add_argument("--repo", default=str(ROOT), help="repository root (default: this repository)")
    args = p.parse_args(argv[1:])
    lines, code = report(args.home, args.repo)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Vendor pinned upstream skill text into plugins/proof, byte for byte.

Commands (run from anywhere; use `python -I tools/vendor.py <command>`):
  sync    download (cached), extract per vendor.json, write vendor.lock.json and NOTICE.md
  check   verify files on disk against vendor.lock.json (offline); exit 1 on drift
  refs    list upstream skills that vendored text mentions but that are not vendored,
          and whether the router (skills/work/SKILL.md) maps each one (offline)
  update  [--source NAME ...] [--to SHA] [--dry-run]
          move each pin to the latest upstream release as vendor.json "track" says (release,
          path, or branch), or to --to SHA for one source; re-sync and add a CHANGELOG line.
          A new commit that changes no vendored file and no version keeps the old pin. --dry-run writes only _scratch/vendor-update.patch.
          Exit 0 up-to-date or updated, 3 updated with unmapped names, 1 on error.

Python standard library only. All upstream bytes are read and written in binary mode.
"""
import argparse
import copy
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "vendor.json"
LOCK = ROOT / "vendor.lock.json"
CACHE = ROOT / ".vendor-cache"
NOTICE = ROOT / "plugins" / "proof" / "NOTICE.md"
ROUTER = ROOT / "plugins" / "proof" / "skills" / "work" / "SKILL.md"
CHANGELOG = ROOT / "CHANGELOG.md"
PATCH = ROOT / "_scratch" / "vendor-update.patch"

# Sync may only write or delete inside these roots. vendor.json must stay inside them.
ALLOWED_ROOTS = (
    "plugins/proof/references",
    "plugins/proof/LICENSES",
    "plugins/proof/skills/grilling",
    "plugins/proof/skills/tdd",
    "plugins/proof/skills/codebase-design",
    "plugins/proof/skills/writing-for-agents",
    "plugins/proof/skills/handoff",
)


LINKS = set()  # symlink and hardlink paths seen in upstream archives


class VendorError(Exception):
    pass


# ---------------------------------------------------------------- config

def load_config():
    cfg = json.loads(CONFIG.read_bytes().decode("utf-8"))
    roots = cfg["managed_roots"]
    for r in roots:
        if r not in ALLOWED_ROOTS:
            raise VendorError(f"managed root not allowed: {r}")
    for name, src in cfg["sources"].items():
        track = src.get("track")
        if not isinstance(track, dict) or track.get("type") not in ("release", "path", "branch"):
            raise VendorError(f"source {name}: 'track' must be one of release, path, branch")
        if track["type"] == "path" and not track.get("path"):
            raise VendorError(f"source {name}: track type 'path' needs a 'path'")
    for rule in cfg["rules"]:
        if rule["source"] not in cfg["sources"]:
            raise VendorError(f"rule uses unknown source: {rule}")
        if rule["type"] not in ("dir", "files", "file"):
            raise VendorError(f"unknown rule type: {rule}")
        if not _in_roots(rule["to"].replace("{name}", "x"), roots):
            raise VendorError(f"rule destination is outside managed roots: {rule['to']}")
    return cfg


def _in_roots(path, roots):
    return any(path == r or path.startswith(r + "/") for r in roots)


def _safe_rel(path):
    parts = path.split("/")
    if not path or path.startswith("/") or ".." in parts or "" in parts or "\\" in path or ":" in path:
        raise VendorError(f"unsafe path: {path!r}")
    return path


# ---------------------------------------------------------------- download

def _tar_path(src):
    return CACHE / f"{src['repo'].replace('/', '__')}-{src['sha']}.tar.gz"


def _tar_ok(path):
    try:
        with tarfile.open(path, "r:gz") as t:
            return t.next() is not None
    except (tarfile.TarError, OSError, EOFError):
        return False


def _download(src):
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = _tar_path(src)
    if dest.exists() and _tar_ok(dest):
        return dest
    tmp = dest.with_suffix(".part")
    url = f"https://codeload.github.com/{src['repo']}/tar.gz/{src['sha']}"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            tmp.write_bytes(resp.read())
    except Exception as exc:  # fall back to the GitHub CLI
        print(f"codeload failed ({exc}); trying gh api", file=sys.stderr)
        try:
            out = subprocess.run(
                ["gh", "api", f"repos/{src['repo']}/tarball/{src['sha']}"],
                capture_output=True, check=False,
            )
        except OSError as exc2:
            tmp.unlink(missing_ok=True)
            raise VendorError(f"cannot download {src['repo']}@{src['sha']}: {exc}; gh unavailable ({exc2})")
        if out.returncode != 0:
            raise VendorError(f"cannot download {src['repo']}@{src['sha']}: {out.stderr.decode(errors='replace')}")
        tmp.write_bytes(out.stdout)
    if not _tar_ok(tmp):
        tmp.unlink(missing_ok=True)
        raise VendorError(f"downloaded archive is not a valid tar.gz: {src['repo']}")
    os.replace(tmp, dest)
    return dest


def _index(tar):
    """Map upstream path (top folder stripped) -> member, regular files only."""
    files = {}
    for m in tar:
        parts = m.name.split("/", 1)
        if len(parts) < 2:
            continue
        if m.issym() or m.islnk():
            LINKS.add(_safe_rel(parts[1]))  # never copied; a link inside a mapped folder is an error
        elif m.isfile():
            files[_safe_rel(parts[1])] = m
    return files


# ---------------------------------------------------------------- planning

def _seg_match(pattern, path):
    ps, xs = pattern.split("/"), path.split("/")
    return len(ps) == len(xs) and all(fnmatch.fnmatchcase(x, p) for p, x in zip(ps, xs))


def _expand(rule, upstream):
    """Return list of (upstream_path, dest_path) for one rule."""
    pat = rule["from"]
    out = []
    if rule["type"] == "file":
        if pat not in upstream:
            raise VendorError(f"upstream file not found: {pat}")
        out.append((pat, rule["to"]))
        matches = 1
    elif rule["type"] == "files":
        hits = sorted(p for p in upstream if _seg_match(pat, p))
        matches = len(hits)
        for p in hits:
            out.append((p, rule["to"] + "/" + p.rsplit("/", 1)[1]))
    else:  # dir
        n = len(pat.split("/"))
        dirs = sorted({"/".join(p.split("/")[:n]) for p in upstream if len(p.split("/")) > n})
        dirs = [d for d in dirs if _seg_match(pat, d)]
        matches = len(dirs)
        for d in dirs:
            if any(l.startswith(d + "/") for l in LINKS):
                raise VendorError(f"link inside mapped folder: {d}")
            dest_dir = rule["to"].replace("{name}", d.rsplit("/", 1)[1])
            for p in sorted(upstream):
                if p.startswith(d + "/"):
                    out.append((p, dest_dir + "/" + p[len(d) + 1:]))
    if matches == 0 or (matches > 1 and not rule.get("multiple")):
        raise VendorError(f"rule matched {matches} items (multiple={bool(rule.get('multiple'))}): {rule['from']}")
    return out


def detect_version(src, tar, index):
    """Read the upstream version from the first of src['version_files'] that has one, with
    src['version_prefix'] in front (Matt Pocock's releases are written v1.3.1). Else "unversioned"."""
    for path in src.get("version_files", []):
        m = index.get(path)
        if m is None:
            continue
        try:
            v = json.loads(tar.extractfile(m).read().decode("utf-8")).get("version")
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(v, str) and v.strip():
            return src.get("version_prefix", "") + v.strip()
    return "unversioned"


def upstream_skill_names(src, index):
    """Names of upstream skills: parent folder of each SKILL.md at the configured depth."""
    root, depth = src["skills_root"], src["skills_depth"]
    names = set()
    for p in index:
        parts = p.split("/")
        if p.startswith(root + "/") and parts[-1] == "SKILL.md" and len(parts) == len(root.split("/")) + depth + 1:
            names.add(parts[-2])
    return sorted(names)


def vendored_skill_names(src, dests):
    """Names of skills that have a folder under src['skills_dest'] among dests."""
    root = src["skills_dest"] + "/"
    return sorted({d[len(root):].split("/")[0] for d in dests if d.startswith(root)})


def build_plan(cfg):
    """Download (cached) every source and return
    {"files": {dest: entry}, "upstream": {source: [names]}, "versions": {source: str},
     "not_vendored": {source: [names]}}."""
    tars = {}
    indexes = {}
    try:
        for name, src in cfg["sources"].items():
            tars[name] = tarfile.open(_download(src), "r:gz")
            indexes[name] = _index(tars[name])
        plan = {}
        for rule in cfg["rules"]:
            for up, dest in _expand(rule, indexes[rule["source"]]):
                _safe_rel(dest)
                if not _in_roots(dest, cfg["managed_roots"]):
                    raise VendorError(f"destination outside managed roots: {dest}")
                if dest in plan:
                    raise VendorError(f"two rules write the same destination: {dest}")
                data = tars[rule["source"]].extractfile(indexes[rule["source"]][up]).read()
                plan[dest] = {
                    "source": rule["source"], "upstream": up, "dest": dest,
                    "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "data": data,
                }
        upstream, versions, not_vendored = {}, {}, {}
        for name, src in cfg["sources"].items():
            upstream[name] = upstream_skill_names(src, indexes[name])
            versions[name] = detect_version(src, tars[name], indexes[name])
            have = set(vendored_skill_names(src, [d for d, e in plan.items() if e["source"] == name]))
            not_vendored[name] = [n for n in upstream[name] if n not in have]
        return {"files": plan, "upstream": upstream, "versions": versions, "not_vendored": not_vendored}
    finally:
        for t in tars.values():
            t.close()


# ---------------------------------------------------------------- notice

def render_notice(cfg, files):
    """files: list of lock entries (dicts with source, dest, size)."""
    L = []
    a = L.append
    a("# Notice")
    a("")
    a("The `proof` plugin vendors third-party skill text byte for byte. "
      "Do not edit the vendored files. This file is generated by `tools/vendor.py sync`.")
    a("")
    a("## Sources")
    a("")
    a("| Name | Repository | Commit | Version | License |")
    a("|---|---|---|---|---|")
    for name, s in cfg["sources"].items():
        lic = s["license_file"].replace("plugins/proof/", "", 1)
        a(f"| {name} | https://github.com/{s['repo']} | `{s['sha']}` | {s['version']} | [{s['license']}]({lic}) |")
    a("")
    a("## Vendored folders")
    a("")
    groups = {}
    for f in files:
        d = f["dest"].replace("plugins/proof/", "", 1)
        parts = d.split("/")
        if d.startswith("references/pstack/skills/"):
            key = "/".join(parts[:4])
        elif d.startswith("references/pstack/agents/"):
            key = "references/pstack/agents"
        elif d.startswith("LICENSES/"):
            key = "LICENSES"
        else:
            key = "/".join(parts[:2])
        groups.setdefault((f["source"], key), 0)
        groups[(f["source"], key)] += 1
    for name in cfg["sources"]:
        a(f"### {name}")
        a("")
        for (src, key), n in sorted(groups.items()):
            if src == name:
                a(f"- `{key}` ({n} file{'s' if n != 1 else ''})")
        a("")
    a("The file `LICENSES/pstack.txt` and `LICENSES/mattpocock-skills.txt` hold the upstream license texts.")
    a("")
    return "\n".join(L)


# ---------------------------------------------------------------- commands

def _write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def _managed_files(cfg):
    found = []
    for r in cfg["managed_roots"]:
        base = ROOT / r
        if base.is_dir():
            for p in base.rglob("*"):
                if p.is_file() or p.is_symlink():
                    found.append(p.relative_to(ROOT).as_posix())
    return sorted(found)


def version_matches(configured, detected):
    """vendor.json may carry '<detected>+<sha7>' for a commit that is not the release itself."""
    return configured == detected or str(configured).startswith(detected + "+")


def cmd_sync(cfg=None, built=None):
    cfg = cfg or load_config()
    built = built or build_plan(cfg)
    plan = built["files"]
    for n, v in built["versions"].items():
        if not version_matches(cfg["sources"][n].get("version"), v):
            print(f"warning: vendor.json version for {n} is {cfg['sources'][n].get('version')!r}, "
                  f"upstream says {v!r}", file=sys.stderr)
    for dest, e in plan.items():
        _write_bytes(ROOT / dest, e["data"])
    removed = []
    for rel in _managed_files(cfg):
        if rel not in plan:
            (ROOT / rel).unlink()
            removed.append(rel)
    # remove empty directories under managed roots (keep the roots)
    for r in cfg["managed_roots"]:
        base = ROOT / r
        if base.is_dir():
            for d in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
                if not any(d.iterdir()):
                    d.rmdir()
    entries = [{k: v for k, v in e.items() if k != "data"} for _, e in sorted(plan.items())]
    entries = [{"source": e["source"], "upstream": e["upstream"], "dest": e["dest"],
                "sha256": e["sha256"], "size": e["size"]} for e in entries]
    lock = {
        "version": 1,
        "sources": {n: {"repo": s["repo"], "sha": s["sha"]} for n, s in cfg["sources"].items()},
        "managed_roots": cfg["managed_roots"],
        "not_vendored": built["not_vendored"],
        "files": entries,
    }
    _write_bytes(LOCK, (json.dumps(lock, indent=2) + "\n").encode("utf-8"))
    _write_bytes(NOTICE, render_notice(cfg, entries).encode("utf-8"))
    print(f"sync: {len(entries)} files written, {len(removed)} removed")
    for r in removed:
        print(f"  removed {r}")
    return 0


def cmd_check():
    cfg = load_config()
    if not LOCK.exists():
        print("DRIFT: vendor.lock.json is missing; run sync")
        return 1
    lock = json.loads(LOCK.read_bytes().decode("utf-8"))
    problems = []
    for n, s in cfg["sources"].items():
        ls = lock["sources"].get(n)
        if not ls or ls["sha"] != s["sha"] or ls["repo"] != s["repo"]:
            problems.append(f"lock source differs from vendor.json: {n}")
    if lock.get("managed_roots") != cfg["managed_roots"]:
        problems.append("lock managed_roots differ from vendor.json")
    nv = lock.get("not_vendored")
    if not isinstance(nv, dict) or set(nv) != set(cfg["sources"]):
        problems.append("lock not_vendored is missing or lists the wrong sources; run sync")
    listed = set()
    for e in lock["files"]:
        listed.add(e["dest"])
        p = ROOT / e["dest"]
        if not p.is_file():
            problems.append(f"missing: {e['dest']}")
            continue
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != e["sha256"] or len(data) != e["size"]:
            problems.append(f"changed: {e['dest']}")
    for rel in _managed_files(cfg):
        if rel not in listed:
            problems.append(f"unlisted file in managed root: {rel}")
    expected = render_notice(cfg, lock["files"]).encode("utf-8")
    if not NOTICE.is_file() or NOTICE.read_bytes() != expected:
        problems.append("plugins/proof/NOTICE.md is missing or stale")
    if problems:
        print(f"DRIFT: {len(problems)} problem(s)")
        for p in problems:
            print("  " + p)
        return 1
    print(f"check: ok ({len(lock['files'])} files)")
    return 0


# ---------------------------------------------------------------- mentions

_TEXT_EXT = {".md", ".txt", ".yaml", ".yml", ".json", ".sh", ".mjs", ".ts", ".js", ".py", ".tsv"}


def mention_patterns(name):
    """Regexes for the ways vendored text refers to a skill. All match whole words only."""
    n = re.escape(name)
    return [
        re.compile(rf"(?<![\w/.\-])/{n}(?![\w\-]|/\w)"),                 # /name  and  `/name`
        re.compile(rf"`{n}`"),                                            # `name`
        re.compile(rf"(?<![\w\-])[Tt]he\s+[`*]*{n}[`*]*\s+skill(?![\w\-])"),  # the name skill, the **name** skill
        re.compile(rf"\*\*{n}\*\*"),                                      # **name**
        re.compile(rf"(?<![\w\-/]){n}/SKILL\.md"),                        # name/SKILL.md
        re.compile(rf"(?<![\w\-])skills/{n}/"),                           # skills/name/
    ]


def find_mentions(texts, names):
    """texts: {path: str}; names: iterable. Returns {name: [paths that mention it]} (mentioned only)."""
    hits = {}
    for name in sorted(set(names)):
        pats = mention_patterns(name)
        for path in sorted(texts):
            if any(p.search(texts[path]) for p in pats):
                hits.setdefault(name, []).append(path)
    return hits


def is_mapped(router_text, name):
    # Limit: any whole-word occurrence in the router counts, so a generic name (such as "pr") can be
    # marked MAPPED by unrelated prose.
    return re.search(rf"(?<![\w\-]){re.escape(name)}(?![\w\-])", router_text) is not None


def analyse_mentions(texts, not_vendored, router_text):
    """Return a sorted list of {name, sources, files, mapped} for every non-vendored skill
    name that the vendored text mentions."""
    sources_of = {}
    for src, names in not_vendored.items():
        for n in names:
            sources_of.setdefault(n, []).append(src)
    hits = find_mentions(texts, sources_of)
    return [{"name": n, "sources": sorted(sources_of[n]), "files": hits[n], "mapped": is_mapped(router_text, n)}
            for n in sorted(hits)]


def _text_files(paths, read):
    return {p: read(p).decode("utf-8", errors="replace")
            for p in paths if PurePosixPath(p).suffix.lower() in _TEXT_EXT}


def _router_text():
    if not ROUTER.is_file():
        raise VendorError(f"router not found: {ROUTER.relative_to(ROOT).as_posix()}")
    return ROUTER.read_bytes().decode("utf-8")


def require_consistent(cfg, lock):
    """Stop when vendor.json and vendor.lock.json name different commits (a half-applied update)."""
    for n, s in cfg["sources"].items():
        ls = lock.get("sources", {}).get(n)
        if not ls or ls.get("sha") != s["sha"]:
            raise VendorError(f"vendor.json and vendor.lock.json disagree for {s.get('label', n)}; "
                              f"run python -I tools/vendor.py sync")


def cmd_refs():
    if not LOCK.is_file():
        raise VendorError("vendor.lock.json is missing; run sync first")
    lock = json.loads(LOCK.read_bytes().decode("utf-8"))
    require_consistent(load_config(), lock)
    nv = lock["not_vendored"]
    texts = _text_files([e["dest"] for e in lock["files"]], lambda p: (ROOT / p).read_bytes())
    found = analyse_mentions(texts, nv, _router_text())
    print("not vendored upstream skills: " + ", ".join(f"{s} {len(v)}" for s, v in sorted(nv.items())))
    if not found:
        print("no vendored text mentions a non-vendored skill")
    for f in found:
        print(f"{f['name']}  {'MAPPED' if f['mapped'] else 'UNMAPPED'}  (not vendored from: {', '.join(f['sources'])})")
        for p in f["files"]:
            print("  " + p)
    bad = [f for f in found if not f["mapped"]]
    print(f"refs: {len(found)} mentioned, {len(found) - len(bad)} mapped, {len(bad)} UNMAPPED")
    return 0


# ---------------------------------------------------------------- update: logic

def diff_plans(old_files, new_files):
    """old_files / new_files: {dest: {"sha256", "source"}}. Returns {"added", "changed", "removed"},
    each a {dest: source} dict."""
    out = {"added": {}, "changed": {}, "removed": {}}
    for d, e in new_files.items():
        if d not in old_files:
            out["added"][d] = e["source"]
        elif old_files[d]["sha256"] != e["sha256"]:
            out["changed"][d] = e["source"]
    for d, e in old_files.items():
        if d not in new_files:
            out["removed"][d] = e["source"]
    return out


def counts_for(diff, source=None):
    return {k: sum(1 for s in v.values() if source in (None, s)) for k, v in diff.items()}


def counts_by_root(diff, roots, source):
    out = {}
    for kind, files in diff.items():
        for d, s in files.items():
            if s != source:
                continue
            root = next((r for r in roots if _in_roots(d, [r])), "(outside managed roots)")
            out.setdefault(root, {"added": 0, "changed": 0, "removed": 0})[kind] += 1
    return out


def is_rule_file(dest):
    """A file that changes how an agent behaves: SKILL.md, a poteto-mode playbook, or an agents/ file."""
    parts = dest.split("/")
    return (parts[-1] == "SKILL.md"
            or "/poteto-mode/playbooks/" in dest
            or "agents" in parts[:-1])


def rule_files(diff, source):
    return sorted(d for kind in diff.values() for d, s in kind.items() if s == source and is_rule_file(d))


def _lines(data):
    parts = data.decode("utf-8").split("\n")
    lines = [x + "\n" for x in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1] + "\n\\ No newline at end of file\n")
    return lines


def make_patch(diff, old_bytes, new_bytes):
    """Unified diff of every added, changed and removed file. old_bytes/new_bytes: dest -> bytes."""
    chunks = []
    for kind in ("changed", "added", "removed"):
        for d in sorted(diff[kind]):
            old = None if kind == "added" else old_bytes(d)
            new = None if kind == "removed" else new_bytes(d)
            head = f"diff --git a/{d} b/{d}\n"
            try:
                ol = _lines(old) if old is not None else []
                nl = _lines(new) if new is not None else []
            except UnicodeDecodeError:
                chunks.append(head + f"Binary files a/{d} and b/{d} differ\n")
                continue
            body = "".join(difflib.unified_diff(
                ol, nl,
                fromfile="/dev/null" if old is None else f"a/{d}",
                tofile="/dev/null" if new is None else f"b/{d}"))
            chunks.append(head + body)
    return "".join(chunks)


def short(sha):
    return sha[:7]


def changelog_line(label, old_version, new_version, old_sha, new_sha, counts):
    return (f"- Upstream {label} {old_version} → {new_version} "
            f"(`{short(old_sha)}` → `{short(new_sha)}`): "
            f"{counts['changed']} changed, {counts['added']} added, {counts['removed']} removed files.")


CHANGELOG_TITLE = (
    "# Changelog\n\n"
    "All notable changes to this project are documented in this file.\n\n"
    "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),\n"
    "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n\n")
_UNRELEASED_RE = re.compile(r"(?m)^## \[Unreleased\][ \t]*$")
_AFTER_CHANGED = ("Deprecated", "Removed", "Fixed", "Security")


def add_changelog_entry(text, line):
    """Add `line` under `## [Unreleased]` -> `### Changed`, creating either heading if missing.
    Returns the new text. A line that is already there is not added twice."""
    nl = "\r\n" if "\r\n" in text else "\n"
    t = text.replace("\r\n", "\n")
    m = _UNRELEASED_RE.search(t)
    if not m:
        nxt = re.search(r"(?m)^## ", t)
        pos = nxt.start() if nxt else len(t)
        head = t[:pos]
        head = head.rstrip("\n") + "\n\n" if head.strip() else CHANGELOG_TITLE
        t = head + "## [Unreleased]\n\n" + t[pos:]
        m = _UNRELEASED_RE.search(t)
    start = m.end()
    nxt = re.compile(r"(?m)^(## |\[[^\]\n]+\]: )").search(t, start)
    end = nxt.start() if nxt else len(t)
    core = t[start:end].strip("\n")
    if line in core.split("\n"):
        return text
    ch = re.search(r"(?m)^### Changed[ \t]*$", core)
    if not core:
        core = "### Changed\n\n" + line
    elif ch:
        nh = re.compile(r"(?m)^### ").search(core, ch.end())
        sec_end = nh.start() if nh else len(core)
        sec = core[ch.start():sec_end].rstrip("\n")
        sec += ("\n\n" if sec.strip() == "### Changed" else "\n") + line
        core = core[:ch.start()] + sec + ("\n\n" + core[sec_end:] if nh else "")
    else:
        later = re.search(r"(?m)^### (?:%s)[ \t]*$" % "|".join(_AFTER_CHANGED), core)
        if later:
            core = core[:later.start()] + "### Changed\n\n" + line + "\n\n" + core[later.start():]
        else:
            core = core + "\n\n### Changed\n\n" + line
    t = t[:start] + "\n\n" + core + "\n" + ("\n" if nxt else "") + t[end:]
    return t.replace("\n", nl) if nl != "\n" else t


def render_report(infos, unmapped, patch_rel, dry_run):
    """infos: one dict per examined source. Returns report lines; the last line is the RESULT line."""
    out = []
    for i in infos:
        if i["up_to_date"]:
            if i.get("kept"):
                out.append(f"{i['label']}: kept pin {short(i['old_sha'])}: it is ahead of (or diverged from) "
                           f"the latest {i['kept']}")
            elif i.get("noop_sha"):
                out.append(f"{i['label']}: up to date (no vendored change at {short(i['noop_sha'])})")
            else:
                out.append(f"{i['label']}: up to date ({i['old_version']}, {short(i['old_sha'])})")
            if i.get("track"):
                out.append(f"  track: {i['track']}")
            continue
        c = i["counts"]
        out.append(f"{i['label']}: {i['old_version']} -> {i['new_version']}  ({short(i['old_sha'])} -> {short(i['new_sha'])})")
        if i.get("track"):
            out.append(f"  track: {i['track']}")
        out.append(f"  files: {c['changed']} changed, {c['added']} added, {c['removed']} removed")
        for root, rc in sorted(i["by_root"].items()):
            out.append(f"    {root}: {rc['changed']} changed, {rc['added']} added, {rc['removed']} removed")
        out.append(f"  rule files changed ({len(i['rule_files'])}):")
        out.extend("    " + f for f in i["rule_files"])
    updated = [i for i in infos if not i["up_to_date"]]
    if updated:
        out.append(f"patch: {patch_rel}")
        out.append(f"UNMAPPED names ({len(unmapped)}): mentioned in vendored text, absent from the router"
                   + (":" if unmapped else ""))
        for f in unmapped:
            out.append(f"  {f['name']}")
            out.extend("    " + p for p in f["files"])
    if dry_run and updated:
        out.append("dry run: nothing applied except the patch file")
    out.append(result_line(infos, unmapped))
    return out


def result_line(infos, unmapped):
    if all(i["up_to_date"] for i in infos):
        return "RESULT: up-to-date"
    return "RESULT: updated, action needed" if unmapped else "RESULT: updated"


# ---------------------------------------------------------------- update: network and files

def _api_json(path):
    """GET a GitHub REST path with urllib (GITHUB_TOKEN is sent when set); `gh api` is the fallback."""
    try:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "proof-vendor",
                   "X-GitHub-Api-Version": "2022-11-28"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request("https://api.github.com/" + path, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"GitHub API via urllib failed ({exc}); trying gh api", file=sys.stderr)
        try:
            out = subprocess.run(["gh", "api", path], capture_output=True, check=False)
        except OSError as exc2:
            raise VendorError(f"cannot read {path}: {exc}; gh unavailable ({exc2})")
        if out.returncode != 0:
            raise VendorError(f"cannot read {path}: {out.stderr.decode(errors='replace').strip()}")
        return json.loads(out.stdout.decode("utf-8"))


def _full_sha(sha, what):
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise VendorError(f"unexpected API answer for {what}")
    return sha


def resolve_commit(repo, ref="HEAD"):
    """Full sha of a commit, tag or branch (default: the default branch tip)."""
    data = _api_json(f"repos/{repo}/commits/{urllib.parse.quote(ref, safe='')}")
    return _full_sha(data.get("sha") if isinstance(data, dict) else None, f"{repo}@{ref}")


def latest_release_tag(repo):
    """Tag of the latest published, non-prerelease GitHub release."""
    data = _api_json(f"repos/{repo}/releases/latest")
    if not isinstance(data, dict) or not data.get("tag_name") or data.get("prerelease") or data.get("draft"):
        raise VendorError(f"{repo}: no usable latest release")
    return data["tag_name"]


def latest_path_commit(repo, path):
    """Latest commit on the default branch that touched `path`."""
    data = _api_json(f"repos/{repo}/commits?path={urllib.parse.quote(path)}&per_page=1")
    if not isinstance(data, list) or not data:
        raise VendorError(f"{repo}: no commit touches {path}")
    return _full_sha(data[0].get("sha"), f"{repo} commit for {path}")


def track_label(track):
    t = track["type"]
    return f"path {track['path']}" if t == "path" else t


def compare_status(repo, base, head):
    """GitHub's verdict on `head` relative to `base`: ahead, behind, identical or diverged."""
    data = _api_json(f"repos/{repo}/compare/{base}...{head}?per_page=1")
    status = data.get("status") if isinstance(data, dict) else None
    if status not in ("ahead", "behind", "identical", "diverged"):
        raise VendorError(f"unexpected compare answer for {repo} {short(base)}...{short(head)}")
    return status


def resolve_target(src, to=None):
    """Return (sha, how it was chosen, name of the target for messages) for one source."""
    repo = src["repo"]
    if to:
        sha = resolve_commit(repo, to)
        return sha, "pinned by --to", short(sha)
    track = src["track"]
    label = track_label(track)
    if track["type"] == "release":
        tag = latest_release_tag(repo)
        return resolve_commit(repo, tag), f"{label} {tag}", f"release {tag}"
    if track["type"] == "path":
        sha = latest_path_commit(repo, track["path"])
    else:
        sha = resolve_commit(repo, "HEAD")
    return sha, label, f"commit {short(sha)}"


def labelled_version(src, detected, sha, release_sha):
    """Version text for vendor.json. Code that is not the release commit gets '+<sha7>'."""
    if src["track"]["type"] == "release" and release_sha and sha != release_sha:
        return f"{detected}+{short(sha)}"
    return detected


def cmd_update(source_names, to, dry_run):
    cfg = load_config()
    names = source_names or list(cfg["sources"])
    for n in names:
        if n not in cfg["sources"]:
            raise VendorError(f"unknown source: {n}")
    if to and len(source_names or []) != 1:
        raise VendorError("--to needs exactly one --source")
    if not LOCK.is_file():
        raise VendorError("vendor.lock.json is missing; run sync first")
    lock = json.loads(LOCK.read_bytes().decode("utf-8"))
    require_consistent(cfg, lock)
    new_cfg = copy.deepcopy(cfg)
    infos = []
    release_shas = {}
    for n, s in cfg["sources"].items():
        if n not in names:
            continue
        new_sha, how, target_name = resolve_target(s, to)
        info = {"name": n, "label": s.get("label", n), "old_version": s["version"], "old_sha": s["sha"],
                "up_to_date": True, "track": how}
        infos.append(info)
        if s["track"]["type"] == "release":
            release_shas[n] = new_sha if not to else resolve_target(s)[0]
        if new_sha == s["sha"]:
            continue
        if not to and compare_status(s["repo"], s["sha"], new_sha) != "ahead":
            # The pin is already ahead of (or has diverged from) the target: never move it backwards.
            info["kept"] = target_name
            continue
        info.update(up_to_date=False, new_sha=new_sha)
        new_cfg["sources"][n]["sha"] = new_sha
    pending = [i for i in infos if not i["up_to_date"]]
    if not pending:
        for line in render_report(infos, [], "", dry_run):
            print(line)
        return 0

    built = build_plan(new_cfg)
    old_files = {e["dest"]: e for e in lock["files"]}
    diff = diff_plans(old_files, built["files"])
    for i in pending:
        n = i["name"]
        i["new_version"] = labelled_version(cfg["sources"][n], built["versions"][n], i["new_sha"],
                                            release_shas.get(n))
        i["counts"] = counts_for(diff, n)
        if not any(i["counts"].values()) and i["new_version"] == i["old_version"]:
            # The pin would move but no vendored file and no version changes: keep the old pin.
            i.update(up_to_date=True, noop_sha=i["new_sha"])
            continue
        i["by_root"] = counts_by_root(diff, cfg["managed_roots"], n)
        i["rule_files"] = rule_files(diff, n)
    pending = [i for i in pending if not i["up_to_date"]]
    if not pending:
        for line in render_report(infos, [], "", dry_run):
            print(line)
        return 0
    texts = _text_files(built["files"], lambda p: built["files"][p]["data"])
    unmapped = [f for f in analyse_mentions(texts, built["not_vendored"], _router_text()) if not f["mapped"]]

    patch = make_patch(diff, lambda d: (ROOT / d).read_bytes(), lambda d: built["files"][d]["data"])
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_bytes(patch.encode("utf-8"))
    patch_rel = PATCH.relative_to(ROOT).as_posix()

    if not dry_run:
        # Everything is downloaded and verified. Write in a safe order: vendored files and lock,
        # then vendor.json, then CHANGELOG. If a step fails, vendor.json still names the old pin
        # and `require_consistent` tells the next run to sync.
        text = CHANGELOG.read_bytes().decode("utf-8") if CHANGELOG.is_file() else ""
        for i in pending:
            new_cfg["sources"][i["name"]]["version"] = i["new_version"]
            text = add_changelog_entry(text, changelog_line(
                i["label"], i["old_version"], i["new_version"], i["old_sha"], i["new_sha"], i["counts"]))
        raw = json.loads(CONFIG.read_bytes().decode("utf-8"))
        for i in pending:
            raw["sources"][i["name"]]["sha"] = i["new_sha"]
            raw["sources"][i["name"]]["version"] = i["new_version"]
        cmd_sync(new_cfg, built)
        CONFIG.write_bytes((json.dumps(raw, indent=2) + "\n").encode("utf-8"))
        if cmd_check() != 0:
            raise VendorError("check failed after sync")
        cmd_refs()
        CHANGELOG.write_bytes(text.encode("utf-8"))
    for line in render_report(infos, unmapped, patch_rel, dry_run):
        print(line)
    return 3 if unmapped else 0


# ---------------------------------------------------------------- main

def main(argv):
    p = argparse.ArgumentParser(prog="vendor.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("sync", "check", "refs"):
        sub.add_parser(c)
    u = sub.add_parser("update")
    u.add_argument("--source", action="append", metavar="NAME", help="source to update (repeatable); default: all")
    u.add_argument("--to", metavar="SHA", help="pin one source to this commit (needs exactly one --source)")
    u.add_argument("--dry-run", action="store_true", help="write only _scratch/vendor-update.patch")
    args = p.parse_args(argv[1:])
    try:
        if args.cmd == "sync":
            return cmd_sync()
        if args.cmd == "check":
            return cmd_check()
        if args.cmd == "refs":
            return cmd_refs()
        return cmd_update(args.source, args.to, args.dry_run)
    except VendorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

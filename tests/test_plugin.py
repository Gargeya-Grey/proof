"""Plugin checks. Run from the repo root: python -I -m unittest discover -s tests -v"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "proof"
SKILLS = PLUGIN / "skills"
VENDOR = ROOT / "tools" / "vendor.py"

ALL_SKILLS = {"work", "grilling", "tdd", "codebase-design", "writing-for-agents", "handoff"}
MODEL_VISIBLE = {"work", "grilling", "tdd", "codebase-design", "writing-for-agents"}
MAX_DESCRIPTION = 1536
MAX_SHORT_DESCRIPTION = 30
MAX_TOTAL_DESCRIPTION = 1200  # always-on cost: all model-visible descriptions together

# Links that are broken in the upstream tree too. Key: (file relative to plugins/proof, link target).
# Reason for every entry: "broken upstream". Fill only after checking the upstream tarball.
BROKEN_UPSTREAM = {
    # Template placeholder "[PR #123](url)"; the file is byte-identical to upstream.
    ("references/pstack/skills/why/references/synthesizer-prompt.md", "url"): "broken upstream",
}

CODEX_SCHEMA_KEYS = {
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
}


def read_json(path):
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def frontmatter(path):
    """Return (dict of top-level scalar keys, raw frontmatter text) for a SKILL.md."""
    text = Path(path).read_bytes().decode("utf-8")
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        raise AssertionError(f"no frontmatter: {path}")
    raw = m.group(1)
    data = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        if val in (">", ">-", "|", "|-", ">+", "|+"):
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            val = (" " if val.startswith(">") else "\n").join(b for b in block).strip()
            data[key] = val
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        data[key] = val
        i += 1
    return data, raw


class VendorTests(unittest.TestCase):
    def test_01_vendor_check_passes(self):
        r = subprocess.run([sys.executable, "-I", str(VENDOR), "check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_08_lock_covers_managed_roots(self):
        lock = read_json(ROOT / "vendor.lock.json")
        cfg = read_json(ROOT / "vendor.json")
        listed = {e["dest"] for e in lock["files"]}
        on_disk = set()
        for r in cfg["managed_roots"]:
            base = ROOT / r
            self.assertTrue(base.is_dir(), f"managed root missing: {r}")
            on_disk |= {p.relative_to(ROOT).as_posix() for p in base.rglob("*") if p.is_file()}
        self.assertEqual(sorted(on_disk - listed), [], "files on disk but not in lock")
        self.assertEqual(sorted(listed - on_disk), [], "files in lock but not on disk")


class ManifestTests(unittest.TestCase):
    def test_02_json_files_parse(self):
        paths = [
            PLUGIN / ".claude-plugin" / "plugin.json",
            PLUGIN / "plugin.json",
            ROOT / ".claude-plugin" / "marketplace.json",
            ROOT / ".agents" / "plugins" / "marketplace.json",
        ]
        for p in paths:
            with self.subTest(path=p.relative_to(ROOT).as_posix()):
                self.assertIsInstance(read_json(p), dict)

    def test_02_claude_manifest_name(self):
        m = read_json(PLUGIN / ".claude-plugin" / "plugin.json")
        self.assertEqual(m["name"], "proof")
        for key in ("skills", "agents", "commands", "hooks", "mcpServers"):
            self.assertNotIn(key, m, f"component key {key} would change what the host scans")

    def test_02_codex_manifest_matches_schema(self):
        m = read_json(PLUGIN / "plugin.json")
        extra = set(m) - CODEX_SCHEMA_KEYS
        self.assertEqual(extra, set(), f"top-level keys the schema does not allow: {extra}")
        self.assertEqual(m["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(m["name"], "proof")
        self.assertRegex(m["name"], r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
        self.assertEqual(set(m["author"]) - {"name", "email", "url"}, set())
        iface = m["extensions"]["com.openai"]["interface"]
        self.assertLessEqual(len(iface["shortDescription"]), MAX_SHORT_DESCRIPTION)
        self.assertEqual(iface["category"], "Developer Tools")
        self.assertEqual(len(iface["defaultPrompt"]), 2)

    def test_02_manifests_agree(self):
        a = read_json(PLUGIN / ".claude-plugin" / "plugin.json")
        b = read_json(PLUGIN / "plugin.json")
        for k in ("name", "version", "description"):
            self.assertEqual(a[k], b[k], k)

    def test_02_marketplaces_point_at_plugin(self):
        c = read_json(ROOT / ".claude-plugin" / "marketplace.json")
        self.assertEqual(c["name"], "gargeya-grey")
        self.assertEqual([(p["name"], p["source"]) for p in c["plugins"]], [("proof", "./plugins/proof")])
        x = read_json(ROOT / ".agents" / "plugins" / "marketplace.json")
        self.assertEqual(x["name"], "gargeya-grey")
        self.assertEqual(len(x["plugins"]), 1)
        self.assertEqual(x["plugins"][0]["name"], "proof")
        self.assertEqual(x["plugins"][0]["source"], {"source": "local", "path": "./plugins/proof"})
        self.assertTrue((ROOT / x["plugins"][0]["source"]["path"] / "plugin.json").is_file())


class SkillTests(unittest.TestCase):
    def skill_dirs(self):
        return {p.name for p in SKILLS.iterdir() if p.is_dir()}

    def test_03_skill_folders(self):
        self.assertEqual(self.skill_dirs(), ALL_SKILLS)
        self.assertEqual([p.name for p in SKILLS.iterdir() if p.is_file()], [], "stray files in skills/")

    def test_03_frontmatter_name_matches_folder(self):
        for d in sorted(self.skill_dirs()):
            with self.subTest(skill=d):
                f = SKILLS / d / "SKILL.md"
                self.assertTrue(f.is_file(), f"missing {f}")
                self.assertEqual(frontmatter(f)[0].get("name"), d)

    def test_04_model_visible_skills(self):
        visible = set()
        total = 0
        for d in sorted(self.skill_dirs()):
            data, raw = frontmatter(SKILLS / d / "SKILL.md")
            if re.search(r"^disable-model-invocation:\s*true\s*$", raw, re.M):
                continue
            visible.add(d)
            desc = data.get("description", "")
            self.assertTrue(desc, f"{d}: empty description")
            self.assertLessEqual(len(desc), MAX_DESCRIPTION, f"{d}: description too long")
            total += len(desc)
        self.assertEqual(visible, MODEL_VISIBLE)
        print(f"\nTotal model-visible description characters: {total} (skills: {', '.join(sorted(visible))})")

    def test_04_total_description_budget(self):
        total = 0
        for d in sorted(self.skill_dirs()):
            data, raw = frontmatter(SKILLS / d / "SKILL.md")
            if not re.search(r"^disable-model-invocation:\s*true\s*$", raw, re.M):
                total += len(data.get("description", ""))
        self.assertLessEqual(total, MAX_TOTAL_DESCRIPTION,
                             "model-visible descriptions grew past the always-on budget")

    def test_05_handoff_is_explicit_only(self):
        _, raw = frontmatter(SKILLS / "handoff" / "SKILL.md")
        self.assertRegex(raw, r"(?m)^disable-model-invocation:\s*true\s*$")
        yaml = (SKILLS / "handoff" / "agents" / "openai.yaml").read_bytes().decode("utf-8")
        self.assertRegex(yaml, r"(?m)^\s*allow_implicit_invocation:\s*false\s*$")

    def test_05_work_has_openai_yaml(self):
        self.assertTrue((SKILLS / "work" / "agents" / "openai.yaml").is_file())

    def test_05_router_paths_exist(self):
        text = (SKILLS / "work" / "SKILL.md").read_text(encoding="utf-8")
        paths = [t for t in re.findall(r"`((?:references|skills)/[^`\s]+)`", text)
                 if "<" not in t and not any(part in ("X", "...") or part.endswith("-X") for part in t.split("/"))]
        self.assertTrue(paths, "router names no concrete paths")
        for t in paths:
            with self.subTest(path=t):
                self.assertTrue((PLUGIN / t).exists(), f"router path does not exist: {t}")


class LicenseTests(unittest.TestCase):
    def test_plugin_license_is_the_root_license(self):
        plugin_license = PLUGIN / "LICENSE"
        self.assertTrue(plugin_license.is_file(), "plugins/proof/LICENSE is missing")
        self.assertEqual(plugin_license.read_bytes(), (ROOT / "LICENSE").read_bytes())


class LayoutTests(unittest.TestCase):
    def test_06_no_stray_skill_files(self):
        refs = PLUGIN / "references"
        for p in PLUGIN.rglob("SKILL.md"):
            if refs in p.parents:
                continue
            rel = p.relative_to(PLUGIN).parts
            self.assertTrue(len(rel) == 3 and rel[0] == "skills", f"stray SKILL.md: {p.relative_to(ROOT)}")

    def test_06_no_component_folders_at_plugin_root(self):
        for name in ("agents", "hooks", "commands", "bin", ".mcp.json"):
            self.assertFalse((PLUGIN / name).exists(), f"{name} must not exist at the plugin root")


def _strip_code(text):
    text = re.sub(r"(?ms)^(```|~~~).*?^\1[^\n]*$", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REFDEF_RE = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")


class LinkTests(unittest.TestCase):
    def test_07_relative_links_resolve(self):
        bad = []
        for md in sorted(PLUGIN.rglob("*.md")):
            text = _strip_code(md.read_bytes().decode("utf-8", errors="replace"))
            targets = LINK_RE.findall(text) + REFDEF_RE.findall(text)
            for t in targets:
                if re.match(r"^(https?:|mailto:|#)", t, re.I) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", t):
                    continue
                path = t.split("#", 1)[0].split("?", 1)[0]
                if not path:
                    continue
                rel_md = md.relative_to(PLUGIN).as_posix()
                if (rel_md, t) in BROKEN_UPSTREAM:
                    continue
                if not (md.parent / path).resolve().exists():
                    bad.append(f"{md.relative_to(ROOT).as_posix()} -> {t}")
        self.assertEqual(bad, [], "broken relative links:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()

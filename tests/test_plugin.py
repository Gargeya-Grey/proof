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
    # statechart is not vendored (3.5 MB of TLA+ tooling); the router maps the name (Overrides).
    ("references/pstack/skills/create-formal-verification-skill/SKILL.md", "../statechart/SKILL.md"): "not vendored",
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
        for name in ("agents", "commands", "bin", ".mcp.json"):  # hooks/ is allowed: DECISIONS.md rule 3
            self.assertFalse((PLUGIN / name).exists(), f"{name} must not exist at the plugin root")


LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REFDEF_RE = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")


# A vendored pstack skill is reached only through a pointer in other text (DECISIONS.md D16).
# These have no pointer anywhere; an agent reaches them only when the user names them.
UNREACHED_PSTACK = {
    "blast-radius": "no pointer upstream; the router has no route for it yet",
    "recall": "no pointer upstream; the router has no route for it yet",
}

# No test here reads Markdown. A line with three backticks or three tildes is a fence marker, wherever
# it sits (in a list, in a quote, indented, with an info string), and the tests never decide which lines
# are code. So: (1) the link test reads every line, and (2) a file with a fence marker is not a source
# of pointers. These files have markers today (paths relative to plugins/proof). A marker in any other
# file, or a file in this set with none, fails test_07_every_vendored_pstack_skill_has_a_pointer.
# Limit: a pointer that exists only in one of these files is not seen (DECISIONS.md D16).
FENCED_TEXT = {
    "references/pstack/skills/how/references/explainer-prompt.md",
    "references/pstack/skills/interrogate/references/reviewer-prompt.md",
    "references/pstack/skills/poteto-mode/playbooks/multi-phase-plan.md",
    "references/pstack/skills/poteto-mode/references/bugbot-triage.md",
    "references/pstack/skills/show-me-your-work/SKILL.md",
    "references/pstack/skills/typescript-best-practices/references/patterns.md",
    "references/pstack/skills/why/references/sources/code-archaeology.md",
    "references/pstack/skills/why/references/sources/databricks.md",
    "references/pstack/skills/why/references/sources/datadog.md",
    "references/pstack/skills/why/references/sources/sentry.md",
    "skills/codebase-design/SKILL.md",
    "skills/grilling/SKILL.md",
    "skills/tdd/mocking.md",
    "skills/tdd/tests.md",
}


def _has_fence(text):
    return "```" in text or "~~~" in text


def _pointer_texts():
    """{path relative to plugins/proof: text} for every file an agent reads and follows.
    NOTICE.md and LICENSES/ list every skill as attribution, so they are not sources."""
    sources = [q for base in (SKILLS, PLUGIN / "references") for pattern in ("*.md", "*.yaml") for q in base.rglob(pattern)]
    return {q.relative_to(PLUGIN).as_posix(): q.read_text(encoding="utf-8") for q in sources}


def _mentions(text, name):
    """A pointer an agent follows: a bold name, a slash name or a backticked name, or a skills/<name>/ path.
    The whole name must match (`/correct-obsolete` is not `correct`)."""
    n = re.escape(name)
    return re.search(rf"\*\*{n}\*\*|/{n}(?![\w-])|`{n}`|skills/{n}/", text)


def _reach_problems(texts):
    """Problems with the pointer texts: a fence marker in an unlisted file, a stale listing, or a vendored
    skill with no pointer (other than the recorded exceptions). Returns a list of messages."""
    problems = [f"{rel}: has a fence marker and is not in FENCED_TEXT" for rel, t in sorted(texts.items())
                if _has_fence(t) and rel not in FENCED_TEXT]
    problems += [f"{rel}: is in FENCED_TEXT but has no fence marker" for rel in sorted(FENCED_TEXT)
                 if rel in texts and not _has_fence(texts[rel])]
    sources = {rel: t for rel, t in texts.items() if not _has_fence(t)}
    leaves = PLUGIN / "references" / "pstack" / "skills"
    unreached = set()
    for leaf in sorted(d for d in leaves.iterdir() if d.is_dir()):
        name = leaf.name
        if name.startswith("principle-") or name == "poteto-mode":
            continue  # poteto-mode's Principles list names each by title; the router names poteto-mode
        own = leaf.relative_to(PLUGIN).as_posix() + "/"
        if not any(_mentions(t, name) for rel, t in sources.items() if not rel.startswith(own)):
            unreached.add(name)
    if unreached != set(UNREACHED_PSTACK):
        problems.append(f"unreached vendored skills {sorted(unreached)} differ from UNREACHED_PSTACK; "
                        "route the skill, or record it there")
    return problems


class ReachTests(unittest.TestCase):
    def test_07_every_vendored_pstack_skill_has_a_pointer(self):
        self.assertEqual(_reach_problems(_pointer_texts()), [])

    def test_07_pointer_matching_rejects_near_names(self):
        self.assertIsNone(_mentions("see /correct-obsolete", "correct"))
        self.assertIsNotNone(_mentions("read `references/pstack/skills/correct/SKILL.md`", "correct"))
        self.assertIsNotNone(_mentions("the **how** skill", "how"))

    def test_07_mutation_a_example_pointer_does_not_replace_a_real_one(self):
        """Mutation A: the only pointer to typescript-best-practices is deleted, and the name stays only
        inside a fenced example whose closing line has four spaces of indent (CommonMark does not close the
        block there). The guard needs no parser: a fence marker anywhere in an unlisted file fails."""
        rel = "references/pstack/skills/principle-type-system-discipline/SKILL.md"
        texts = _pointer_texts()
        self.assertEqual(_reach_problems(texts), [], "the real text must pass")
        pointer = "For TypeScript syntax, see the `typescript-best-practices` skill."
        self.assertIn(pointer, texts[rel])
        for example in ("Example:\n```\nsee the `typescript-best-practices` skill\n    ```\n",
                        "- item\n  ```\n  `typescript-best-practices`\n  ```\n"):
            mutated = dict(texts, **{rel: texts[rel].replace(pointer, "") + example})
            self.assertTrue(_mentions(mutated[rel], "typescript-best-practices"), "a bare search would be fooled")
            problems = _reach_problems(mutated)
            self.assertTrue(any(rel in p and "fence marker" in p for p in problems), problems)
        # Deleting the pointer and adding nothing is caught too.
        gone = dict(texts, **{rel: texts[rel].replace(pointer, "")})
        self.assertTrue(any("unreached" in p for p in _reach_problems(gone)))

    def test_07_router_has_no_code_fence(self):
        """The router is the one file of this plugin that is not vendored. It holds no fenced block, so
        every line of it is prose that an agent follows."""
        for q in sorted((SKILLS / "work").rglob("*")):
            if q.is_file():
                with self.subTest(file=q.relative_to(ROOT).as_posix()):
                    self.assertFalse(_has_fence(q.read_bytes().decode("utf-8", errors="replace")))

    def test_07_router_enters_the_hub(self):
        text = (SKILLS / "work" / "SKILL.md").read_text(encoding="utf-8")
        hub = "`references/pstack/skills/poteto-mode/SKILL.md`"
        self.assertIn(f"- Anything larger: read {hub} in full", text, "the size rule must send larger tasks to the hub")
        summary_row = [line for line in text.splitlines() if line.startswith("| Continue after a context summary")]
        self.assertEqual(len(summary_row), 1, "the router needs one context-summary route")
        self.assertIn(hub, summary_row[0])

    def test_07_router_routes_escapes(self):
        """The wording of the route: the required sentences are present and the listed negations are absent.
        It does not check that the route means the right thing; tests/router-scenarios.md checks what a
        small model does with it (DECISIONS.md D16)."""
        text = (SKILLS / "work" / "SKILL.md").read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if line.startswith("| Fix an escape")]
        self.assertEqual(len(rows), 1, "the router needs one escape route")
        route = rows[0].split(" | ", 1)[1]
        sentences = [x.strip() for x in re.split(r"(?<=\.) ", route)]
        self.assertTrue(sentences[0].startswith("Read `references/pstack/skills/correct/SKILL.md` and apply it"),
                        "the route must start by reading correct")
        self.assertIn("Find every instance of the class before you fix one, and add the check of your own that should have found it.",
                      sentences)
        premise = [x for x in sentences if "principle-attack-the-premise" in x]
        self.assertEqual(len(premise), 1)
        self.assertTrue(premise[0].startswith("When the same class comes back after your class fix, read "))
        self.assertTrue(premise[0].endswith(" before the next fix."))
        for word in (" not ", "never", "ignore", "skip", "only the reported", "instead"):
            self.assertNotIn(word, f" {route.lower()} ", f"the escape route must not contain {word!r}")
        summary = [line for line in text.splitlines() if line.startswith("| Continue after a context summary")]
        self.assertTrue(summary[0].split(" | ", 1)[1].startswith(
            "Before the next step, read `references/pstack/skills/poteto-mode/SKILL.md` again, and every playbook, principle and skill file"))

    def test_07_router_reports_missing_hooks(self):
        """The hooks only reinforce the router (DECISIONS.md rule 3). The summary row must say what the
        hook notice looks like, and what to do when it is missing, so a host without hooks is visible."""
        text = (SKILLS / "work" / "SKILL.md").read_text(encoding="utf-8")
        row = [line for line in text.splitlines() if line.startswith("| Continue after a context summary")][0]
        self.assertIn("a notice that starts with `proof:` follows the summary", row)
        self.assertIn("When the summary has no `proof:` notice beside it, the hooks are not active on this host: "
                      "tell the user once per session, then do this row yourself.", row)

    def test_07_router_routes_parallel_units_and_formal_proof(self):
        text = (SKILLS / "work" / "SKILL.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        units = [line for line in lines if line.startswith("| Split work into units for parallel subagents")]
        self.assertEqual(len(units), 1, "the router needs one parallel-units route")
        for part in ("write a task file before any worker starts", "Economy worker contract",
                     "one review of the combined diff against the task file"):
            self.assertIn(part, units[0])
        swarm = [line for line in lines if line.startswith("| swarm, Orchestrate")]
        self.assertEqual(len(swarm), 1)
        self.assertIn("parallel-units route", swarm[0])
        formal = [line for line in lines if line.startswith("| Prove an invariant")]
        self.assertEqual(len(formal), 1, "the router needs one formal-verification route")
        for name in ("create-formal-verification-skill", "maintain-formal-verification-skill"):
            self.assertIn(f"`references/pstack/skills/{name}/SKILL.md`", formal[0])

    def test_07_late_triggers_are_always_visible(self):
        desc = frontmatter(SKILLS / "work" / "SKILL.md")[0].get("description", "")
        self.assertIn("after a context summary", desc)
        self.assertIn("escape", desc)

    def test_07_every_principle_is_named_by_the_hub(self):
        hub = (PLUGIN / "references" / "pstack" / "skills" / "poteto-mode" / "SKILL.md").read_text(encoding="utf-8")
        titles = {re.sub(r"[^a-z0-9-]", "", t.lower().replace(" ", "-"))
                  for t in re.findall(r"^- \*\*([^*]+?)\.?\*\*", hub, re.M)}
        titles |= set(re.findall(r"\*\*principle-([a-z0-9-]+)\*\*", hub))
        for leaf in sorted((PLUGIN / "references" / "pstack" / "skills").glob("principle-*")):
            with self.subTest(principle=leaf.name):
                self.assertIn(leaf.name.removeprefix("principle-"), titles)


def _broken_links(text, base_dir, rel_md=""):
    """Relative link targets in text that do not resolve from base_dir. Every line is read, fenced or not:
    a link in a code example is a link too, and an example that is not a file goes in BROKEN_UPSTREAM."""
    bad = []
    for t in LINK_RE.findall(text) + REFDEF_RE.findall(text):
        if re.match(r"^(https?:|mailto:|#)", t, re.I) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", t):
            continue
        path = t.split("#", 1)[0].split("?", 1)[0]
        if not path or (rel_md, t) in BROKEN_UPSTREAM:
            continue
        if not (base_dir / path).resolve().exists():
            bad.append(t)
    return bad


class LinkTests(unittest.TestCase):
    def test_07_relative_links_resolve(self):
        bad = []
        for md in sorted(PLUGIN.rglob("*.md")):
            text = md.read_bytes().decode("utf-8", errors="replace")
            rel_md = md.relative_to(PLUGIN).as_posix()
            bad += [f"{md.relative_to(ROOT).as_posix()} -> {t}" for t in _broken_links(text, md.parent, rel_md)]
        self.assertEqual(bad, [], "broken relative links:\n" + "\n".join(bad))

    def test_07_mutation_b_broken_link_after_a_fence_is_found(self):
        """Mutation B: a broken link follows a fenced block inside a list item. Fences are not parsed,
        so every line is read."""
        self.assertEqual(_broken_links("- item\n  ```\n  code\n  ```\n\n[broken](missing-file.md)\n", ROOT), ["missing-file.md"])
        self.assertEqual(_broken_links("> ```\n> code\n\n[broken](missing-file.md)\n", ROOT), ["missing-file.md"])
        self.assertEqual(_broken_links("[ok](README.md)\n- item\n  ```\n  code\n  ```\n", ROOT), [], "the real text passes")


if __name__ == "__main__":
    unittest.main()

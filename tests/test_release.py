"""Tests for tools/release.py. They use fixtures in a temp folder, never the real tree."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toolload import ROOT, load

release = load("release")

CLAUDE = "plugins/proof/.claude-plugin/plugin.json"
CODEX = "plugins/proof/plugin.json"

CLAUDE_TEXT = '{\n  "name": "proof",\n  "version": "0.1.0",\n  "description": "d",\n  "keywords": ["a"]\n}\n'
CODEX_TEXT = ('{\n  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",\n'
              '  "name": "proof",\n  "version": "0.1.0",\n  "extensions": {"com.openai": {"interface": {}}}\n}\n')
VENDOR = {
    "sources": {
        "pstack": {"label": "pstack", "version": "0.15.20", "sha": "1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def"},
        "mattpocock": {"label": "mattpocock/skills", "version": "v1.3.1",
                       "sha": "24fe0ef7737efae15c87225755e9f6f5965e4888"},
    }
}
UPSTREAM = "Upstream: pstack 0.15.20 (`1b6d44f`), mattpocock/skills v1.3.1 (`24fe0ef`)."
TITLE = "# Changelog\n\nAll notable changes.\n\n"
CHANGELOG = (TITLE + "## [Unreleased]\n\n### Added\n\n- New thing.\n\n### Fixed\n\n- Old bug.\n\n"
             "## [0.1.0] - 2026-10-12\n\n### Added\n\n- First build.\n\n" + UPSTREAM + "\n")


def make_root(tmp, claude=CLAUDE_TEXT, codex=CODEX_TEXT, changelog=CHANGELOG, vendor=VENDOR):
    root = Path(tmp)
    for rel, text in ((CLAUDE, claude), (CODEX, codex), ("CHANGELOG.md", changelog),
                      ("vendor.json", json.dumps(vendor))):
        if text is None:
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    return root


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in Path(root).rglob("*") if p.is_file()}


class VersionTests(unittest.TestCase):
    def test_next_version(self):
        self.assertEqual(release.next_version("0.1.0", "patch"), "0.1.1")
        self.assertEqual(release.next_version("0.1.9", "minor"), "0.2.0")
        self.assertEqual(release.next_version("1.2.3", "major"), "2.0.0")

    def test_next_version_refuses_prerelease_and_invalid(self):
        for bad in ("1.0", "01.0.0", "1.0.0-rc.1", "1.0.0+build", "v1.0.0"):
            with self.subTest(v=bad), self.assertRaises(release.ReleaseError):
                release.next_version(bad, "patch")

    def test_semver_regex(self):
        for ok in ("0.0.0", "1.0.0-alpha.1", "1.0.0+20130313144700", "10.20.30"):
            self.assertTrue(release.SEMVER_RE.match(ok), ok)
        for bad in ("1", "1.2", "1.2.3.4", "1.02.3", "1.2.3-", "a.b.c"):
            self.assertFalse(release.SEMVER_RE.match(bad), bad)

    def test_set_version_text_changes_only_the_value(self):
        out = release.set_version_text(CLAUDE_TEXT, "0.2.0")
        self.assertEqual(out, CLAUDE_TEXT.replace('"0.1.0"', '"0.2.0"'))
        with self.assertRaises(release.ReleaseError):
            release.set_version_text('{"name": "x"}', "1.0.0")
        with self.assertRaises(release.ReleaseError):
            release.set_version_text('{"version": "1.0.0", "x": {"version": "2"}}', "1.0.1")

    def test_upstream_line(self):
        self.assertEqual(release.upstream_line(VENDOR), UPSTREAM)


class BumpTests(unittest.TestCase):
    def setUp(self):
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def test_bump_minor_writes_all_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            self.assertEqual(release.cmd_bump(root, "minor", "2026-11-01", False), 0)
            self.assertEqual((root / CLAUDE).read_text(encoding="utf-8"), CLAUDE_TEXT.replace("0.1.0", "0.2.0"))
            self.assertEqual((root / CODEX).read_text(encoding="utf-8"), CODEX_TEXT.replace("0.1.0", "0.2.0"))
            expected = (TITLE + "## [Unreleased]\n\n## [0.2.0] - 2026-11-01\n\n### Added\n\n- New thing.\n\n"
                        "### Fixed\n\n- Old bug.\n\n" + UPSTREAM + "\n\n"
                        "## [0.1.0] - 2026-10-12\n\n### Added\n\n- First build.\n\n" + UPSTREAM + "\n")
            self.assertEqual((root / "CHANGELOG.md").read_text(encoding="utf-8"), expected)
            self.assertEqual(release.check_problems(root), [])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            before = snapshot(root)
            self.assertEqual(release.cmd_bump(root, "patch", "2026-11-01", True), 0)
            self.assertEqual(snapshot(root), before)

    def test_refuses_empty_unreleased(self):
        for body in ("", "### Added\n\n", "Some prose but no bullet.\n"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                root = make_root(tmp, changelog=TITLE + "## [Unreleased]\n\n" + body + "\n## [0.1.0] - 2026-10-12\n\n"
                                 + UPSTREAM + "\n")
                before = snapshot(root)
                with self.assertRaises(release.ReleaseError):
                    release.cmd_bump(root, "patch", "2026-11-01", False)
                self.assertEqual(snapshot(root), before)

    def test_refuses_disagreeing_manifests_bad_date_and_missing_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, codex=CODEX_TEXT.replace("0.1.0", "0.1.1"))
            with self.assertRaises(release.ReleaseError):
                release.cmd_bump(root, "patch", "2026-11-01", False)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            for bad in ("2026-13-01", "11/01/2026", "2026-1-1"):
                with self.subTest(date=bad), self.assertRaises(release.ReleaseError):
                    release.cmd_bump(root, "patch", bad, False)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, changelog=TITLE + "## [0.1.0] - 2026-10-12\n")
            with self.assertRaises(release.ReleaseError):
                release.cmd_bump(root, "patch", "2026-11-01", False)

    def test_bump_when_unreleased_is_the_only_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, changelog=TITLE + "## [Unreleased]\n\n- One.\n")
            release.cmd_bump(root, "major", "2026-11-01", False)
            self.assertEqual((root / "CHANGELOG.md").read_text(encoding="utf-8"),
                             TITLE + "## [Unreleased]\n\n## [1.0.0] - 2026-11-01\n\n- One.\n\n" + UPSTREAM + "\n")

    def test_cli_runs_without_git_and_prints_tag_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "release.py"), "--root", str(root),
                                "bump", "patch", "--date", "2026-11-01"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("claude plugin tag plugins/proof", r.stdout)
            self.assertNotIn("git ", r.stdout)
            self.assertEqual(release.read_version(root, CLAUDE), "0.1.1")


class CheckTests(unittest.TestCase):
    def problems(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            return release.check_problems(make_root(tmp, **kw))

    def test_passes_on_consistent_fixture(self):
        self.assertEqual(self.problems(), [])

    def test_fails_when_versions_differ(self):
        out = self.problems(codex=CODEX_TEXT.replace("0.1.0", "0.1.1"))
        self.assertTrue(any("manifests disagree" in p for p in out), out)

    def test_fails_on_invalid_semver(self):
        out = self.problems(claude=CLAUDE_TEXT.replace("0.1.0", "0.1"), codex=CODEX_TEXT.replace("0.1.0", "0.1"))
        self.assertTrue(any("SemVer" in p for p in out), out)

    def test_fails_without_changelog_section(self):
        out = self.problems(claude=CLAUDE_TEXT.replace("0.1.0", "0.2.0"), codex=CODEX_TEXT.replace("0.1.0", "0.2.0"))
        self.assertTrue(any("no '## [0.2.0]" in p for p in out), out)

    def test_fails_without_changelog_file(self):
        out = self.problems(changelog=None)
        self.assertTrue(any("CHANGELOG.md" in p for p in out), out)

    def test_fails_when_upstream_line_differs_or_is_missing(self):
        out = self.problems(changelog=CHANGELOG.replace("`1b6d44f`", "`abcdef0`"))
        self.assertTrue(any("differs from vendor.json" in p for p in out), out)
        out = self.problems(changelog=CHANGELOG.replace(UPSTREAM + "\n", ""))
        self.assertTrue(any("no 'Upstream:' line" in p for p in out), out)

    def test_upstream_line_of_another_section_does_not_count(self):
        text = (TITLE + "## [Unreleased]\n\n## [0.2.0] - 2026-11-01\n\n- x\n\n"
                "## [0.1.0] - 2026-10-12\n\n- y\n\n" + UPSTREAM + "\n")
        out = self.problems(claude=CLAUDE_TEXT.replace("0.1.0", "0.2.0"),
                            codex=CODEX_TEXT.replace("0.1.0", "0.2.0"), changelog=text)
        self.assertTrue(any("no 'Upstream:' line" in p for p in out), out)

    PENDING_LINE = ("- Upstream pstack 0.15.20 \u2192 0.15.21 (`1b6d44f` \u2192 `ccb5507`): "
                    "1 changed, 0 added, 0 removed files.")

    def pending_root(self, tmp, label_in_line="pstack", changelog=None):
        vendor = json.loads(json.dumps(VENDOR))
        vendor["sources"]["pstack"].update(version="0.15.21", sha="ccb5507" + "0" * 33)
        text = changelog or CHANGELOG.replace(
            "## [Unreleased]\n\n", "## [Unreleased]\n\n### Changed\n\n"
            + self.PENDING_LINE.replace("pstack", label_in_line, 1) + "\n\n", 1)
        return make_root(tmp, changelog=text, vendor=vendor)

    def test_pending_source_may_differ_from_last_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.pending_root(tmp)
            self.assertEqual(release.check_problems(root), [])
            self.assertEqual(release.pending_sources(root), ["pstack"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(release.cmd_check(root), 0)
            self.assertIn("pending release: pstack\n", out.getvalue())
            self.assertIn("release check: ok", out.getvalue())

    def test_pin_change_without_unreleased_line_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.pending_root(tmp, changelog=CHANGELOG)
            self.assertEqual(release.pending_sources(root), [])
            self.assertTrue(any("differs from vendor.json" in p for p in release.check_problems(root)))

    def test_pending_label_must_match_whole_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.pending_root(tmp, label_in_line="pstack-other")
            self.assertEqual(release.pending_sources(root), [])
            self.assertTrue(release.check_problems(root))

    def test_other_source_is_still_compared_while_one_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.pending_root(tmp)
            vend = json.loads((root / "vendor.json").read_text(encoding="utf-8"))
            vend["sources"]["mattpocock"]["sha"] = "f" * 40
            (root / "vendor.json").write_text(json.dumps(vend), encoding="utf-8")
            out = release.check_problems(root)
            self.assertEqual(len(out), 1, out)
            self.assertIn("mattpocock/skills v1.3.1 (`fffffff`)", out[0])

    def test_pending_release_does_not_excuse_a_missing_upstream_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.pending_root(tmp)
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8").replace(UPSTREAM + "\n", "")
            (root / "CHANGELOG.md").write_text(text, encoding="utf-8")
            self.assertTrue(any("no 'Upstream:' line" in p for p in release.check_problems(root)))

    def test_cli_prints_one_line_per_failure_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, codex=CODEX_TEXT.replace("0.1.0", "0.1.1"))
            r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "release.py"), "--root", str(root),
                                "check"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertTrue(all(l.startswith("FAIL: ") for l in r.stdout.splitlines() if l.strip()), r.stdout)


if __name__ == "__main__":
    unittest.main()

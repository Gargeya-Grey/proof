"""Tests for the update, refs and changelog logic in tools/vendor.py. No network."""
import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toolload import ROOT, load

vendor = load("vendor")


def entry(source, data):
    return {"source": source, "sha256": hashlib.sha256(data).hexdigest(), "data": data}


P = "plugins/proof/references/pstack"
M = "plugins/proof/skills"


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            f"{P}/skills/how/SKILL.md": entry("pstack", b"how v1\n"),
            f"{P}/skills/why/SKILL.md": entry("pstack", b"why\n"),
            f"{P}/skills/gone/SKILL.md": entry("pstack", b"gone\n"),
            f"{M}/tdd/SKILL.md": entry("mattpocock", b"tdd v1\n"),
            f"{M}/tdd/tests.md": entry("mattpocock", b"same\n"),
        }
        self.new = {
            f"{P}/skills/how/SKILL.md": entry("pstack", b"how v2\n"),
            f"{P}/skills/why/SKILL.md": entry("pstack", b"why\n"),
            f"{P}/skills/poteto-mode/playbooks/bug-fix.md": entry("pstack", b"fix\n"),
            f"{P}/agents/helper.md": entry("pstack", b"agent\n"),
            f"{M}/tdd/SKILL.md": entry("mattpocock", b"tdd v1\n"),
            f"{M}/tdd/tests.md": entry("mattpocock", b"same\n"),
        }
        self.diff = vendor.diff_plans(self.old, self.new)

    def test_diff_plans(self):
        self.assertEqual(sorted(self.diff["changed"]), [f"{P}/skills/how/SKILL.md"])
        self.assertEqual(sorted(self.diff["added"]),
                         [f"{P}/agents/helper.md", f"{P}/skills/poteto-mode/playbooks/bug-fix.md"])
        self.assertEqual(sorted(self.diff["removed"]), [f"{P}/skills/gone/SKILL.md"])

    def test_counts_per_source(self):
        self.assertEqual(vendor.counts_for(self.diff, "pstack"), {"added": 2, "changed": 1, "removed": 1})
        self.assertEqual(vendor.counts_for(self.diff, "mattpocock"), {"added": 0, "changed": 0, "removed": 0})
        self.assertEqual(vendor.counts_for(self.diff), {"added": 2, "changed": 1, "removed": 1})

    def test_counts_by_root(self):
        roots = ["plugins/proof/references", "plugins/proof/skills/tdd"]
        self.assertEqual(vendor.counts_by_root(self.diff, roots, "pstack"),
                         {"plugins/proof/references": {"added": 2, "changed": 1, "removed": 1}})

    def test_rule_files(self):
        self.assertEqual(vendor.rule_files(self.diff, "pstack"), [
            f"{P}/agents/helper.md",
            f"{P}/skills/gone/SKILL.md",
            f"{P}/skills/how/SKILL.md",
            f"{P}/skills/poteto-mode/playbooks/bug-fix.md",
        ])
        self.assertEqual(vendor.rule_files(self.diff, "mattpocock"), [])

    def test_is_rule_file(self):
        yes = [f"{P}/skills/x/SKILL.md", f"{P}/skills/poteto-mode/playbooks/a.md", f"{P}/agents/a.md",
               f"{M}/tdd/agents/openai.yaml"]
        no = [f"{P}/skills/x/references/a.md", f"{P}/skills/poteto-mode/references/a.md",
              f"{P}/skills/x/agents-notes.md", "plugins/proof/LICENSES/pstack.txt"]
        for p in yes:
            self.assertTrue(vendor.is_rule_file(p), p)
        for p in no:
            self.assertFalse(vendor.is_rule_file(p), p)


class PatchTests(unittest.TestCase):
    def test_patch_shows_change_add_remove_binary_and_eof(self):
        diff = {"changed": {"a.md": "s", "n.md": "s"}, "added": {"b.md": "s", "bin.dat": "s"},
                "removed": {"c.md": "s"}}
        old = {"a.md": b"one\ntwo\n", "n.md": b"x\n", "c.md": b"bye\n"}
        new = {"a.md": b"one\nTWO\n", "n.md": b"x", "b.md": b"hello\n", "bin.dat": b"\xff\xfe"}
        patch = vendor.make_patch(diff, old.__getitem__, new.__getitem__)
        self.assertIn("diff --git a/a.md b/a.md\n--- a/a.md\n+++ b/a.md\n", patch)
        self.assertIn("-two\n+TWO\n", patch)
        self.assertIn("--- /dev/null\n+++ b/b.md\n", patch)
        self.assertIn("+hello\n", patch)
        self.assertIn("--- a/c.md\n+++ /dev/null\n", patch)
        self.assertIn("-bye\n", patch)
        self.assertIn("Binary files a/bin.dat and b/bin.dat differ", patch)
        self.assertIn("\\ No newline at end of file", patch)

    def test_empty_diff_gives_empty_patch(self):
        self.assertEqual(vendor.make_patch({"changed": {}, "added": {}, "removed": {}}, None, None), "")


class ReportTests(unittest.TestCase):
    def info(self, **kw):
        base = {"name": "pstack", "label": "pstack", "old_version": "0.15.20", "old_sha": "1" * 40,
                "up_to_date": False, "new_sha": "2" * 40, "new_version": "0.15.21",
                "counts": {"changed": 3, "added": 1, "removed": 2},
                "by_root": {"plugins/proof/references": {"changed": 3, "added": 1, "removed": 2}},
                "rule_files": [f"{P}/skills/how/SKILL.md"]}
        base.update(kw)
        return base

    def test_changelog_line(self):
        line = vendor.changelog_line("pstack", "0.15.20", "0.15.21", "1b6d44ff26d4", "ccb5507cec15",
                                     {"changed": 3, "added": 1, "removed": 2})
        self.assertEqual(line, "- Upstream pstack 0.15.20 → 0.15.21 (`1b6d44f` → `ccb5507`): "
                               "3 changed, 1 added, 2 removed files.")

    def test_result_lines(self):
        up = {"up_to_date": True}
        self.assertEqual(vendor.result_line([up, up], []), "RESULT: up-to-date")
        self.assertEqual(vendor.result_line([up, self.info()], []), "RESULT: updated")
        self.assertEqual(vendor.result_line([self.info()], [{"name": "x", "files": []}]),
                         "RESULT: updated, action needed")

    def test_report_content_and_last_line(self):
        unmapped = [{"name": "newskill", "files": [f"{P}/skills/how/SKILL.md"]}]
        lines = vendor.render_report([self.info(), {"name": "m", "label": "mattpocock/skills", "up_to_date": True,
                                                    "old_version": "v1.3.1", "old_sha": "3" * 40}],
                                     unmapped, "_scratch/vendor-update.patch", False)
        text = "\n".join(lines)
        self.assertIn("pstack: 0.15.20 -> 0.15.21  (1111111 -> 2222222)", text)
        self.assertIn("files: 3 changed, 1 added, 2 removed", text)
        self.assertIn("mattpocock/skills: up to date (v1.3.1, 3333333)", text)
        self.assertIn("patch: _scratch/vendor-update.patch", text)
        self.assertIn(f"    {P}/skills/how/SKILL.md", text)
        self.assertIn("newskill", text)
        self.assertEqual(lines[-1], "RESULT: updated, action needed")

    def test_report_names_track_and_noop_pin(self):
        lines = vendor.render_report([
            self.info(track="release v1.3.2"),
            {"name": "m", "label": "mattpocock/skills", "up_to_date": True, "old_version": "v1.3.1",
             "old_sha": "3" * 40, "noop_sha": "4" * 40, "track": "path pstack/plugin.json"}],
            [], "p.patch", True)
        text = "\n".join(lines)
        self.assertIn("  track: release v1.3.2", text)
        self.assertIn("mattpocock/skills: up to date (no vendored change at 4444444)\n  track: path pstack/plugin.json",
                      text)

    def test_report_when_everything_is_current(self):
        lines = vendor.render_report([{"name": "p", "label": "pstack", "up_to_date": True,
                                       "old_version": "0.15.20", "old_sha": "1" * 40}], [], "", True)
        self.assertEqual(lines[-1], "RESULT: up-to-date")
        self.assertNotIn("patch:", "\n".join(lines))


class ChangelogWriterTests(unittest.TestCase):
    LINE = "- Upstream pstack 1 → 2 (`aaaaaaa` → `bbbbbbb`): 1 changed, 0 added, 0 removed files."

    def test_creates_unreleased_and_changed_when_file_empty(self):
        out = vendor.add_changelog_entry("", self.LINE)
        self.assertTrue(out.startswith("# Changelog\n"))
        self.assertTrue(out.endswith("## [Unreleased]\n\n### Changed\n\n" + self.LINE + "\n"), out)

    def test_creates_unreleased_above_first_release(self):
        text = "# Changelog\n\nIntro.\n\n## [0.1.0] - 2026-10-12\n\n- a\n"
        out = vendor.add_changelog_entry(text, self.LINE)
        self.assertEqual(out, "# Changelog\n\nIntro.\n\n## [Unreleased]\n\n### Changed\n\n" + self.LINE
                         + "\n\n## [0.1.0] - 2026-10-12\n\n- a\n")

    def test_adds_changed_heading_in_order(self):
        text = "# C\n\n## [Unreleased]\n\n### Added\n\n- x\n\n### Fixed\n\n- y\n\n## [0.1.0] - d\n\n- a\n"
        out = vendor.add_changelog_entry(text, self.LINE)
        self.assertEqual(out, "# C\n\n## [Unreleased]\n\n### Added\n\n- x\n\n### Changed\n\n" + self.LINE
                         + "\n\n### Fixed\n\n- y\n\n## [0.1.0] - d\n\n- a\n")

    def test_appends_to_existing_changed_section(self):
        text = "# C\n\n## [Unreleased]\n\n### Changed\n\n- first\n\n### Fixed\n\n- y\n\n## [0.1.0] - d\n"
        out = vendor.add_changelog_entry(text, self.LINE)
        self.assertEqual(out, "# C\n\n## [Unreleased]\n\n### Changed\n\n- first\n" + self.LINE
                         + "\n\n### Fixed\n\n- y\n\n## [0.1.0] - d\n")

    def test_does_not_touch_older_changed_sections(self):
        text = "# C\n\n## [Unreleased]\n\n### Added\n\n- x\n\n## [0.1.0] - d\n\n### Changed\n\n- old\n"
        out = vendor.add_changelog_entry(text, self.LINE)
        self.assertTrue(out.endswith("## [0.1.0] - d\n\n### Changed\n\n- old\n"), out)
        self.assertEqual(out.count("### Changed"), 2)

    def test_same_line_twice_is_added_once(self):
        once = vendor.add_changelog_entry("# C\n", self.LINE)
        self.assertEqual(vendor.add_changelog_entry(once, self.LINE), once)

    def test_two_sources_two_lines(self):
        other = self.LINE.replace("pstack", "mattpocock/skills")
        out = vendor.add_changelog_entry(vendor.add_changelog_entry("# C\n", self.LINE), other)
        self.assertIn(self.LINE + "\n" + other + "\n", out)

    def test_keeps_crlf(self):
        out = vendor.add_changelog_entry("# C\r\n\r\n## [Unreleased]\r\n\r\n### Added\r\n\r\n- x\r\n", self.LINE)
        self.assertNotRegex(out, r"(?<!\r)\n")


class MentionTests(unittest.TestCase):
    def hit(self, text, name="swarm"):
        return name in vendor.find_mentions({"f.md": text}, [name])

    def test_forms_that_match(self):
        for text in ("Use /swarm now", "Use `/swarm` now", "Use `swarm` now", "the swarm skill", "The swarm skill",
                     "the **swarm** skill", "the `swarm` skill", "see **swarm**", "read swarm/SKILL.md",
                     "path skills/swarm/ here", "(/swarm)"):
            with self.subTest(text=text):
                self.assertTrue(self.hit(text), text)

    def test_whole_words_only(self):
        for text in ("swarm", "a swarm of bees", "the swarmy skill", "/swarm-mode", "/swarmed", "a/swarm/b",
                     "https://example.com/swarm", "myswarm/SKILL.md", "skills/swarm-two/", "**swarmed**",
                     "`swarm-x`", "the swarm-x skill"):
            with self.subTest(text=text):
                self.assertFalse(self.hit(text), text)

    def test_hyphenated_names(self):
        self.assertTrue(self.hit("run /setup-pstack first", "setup-pstack"))
        self.assertFalse(self.hit("run /setup-pstack-more first", "setup-pstack"))

    def test_is_mapped_whole_word(self):
        self.assertTrue(vendor.is_mapped("| swarm, Orchestrate |", "swarm"))
        self.assertFalse(vendor.is_mapped("swarmed and swarm-x", "swarm"))
        self.assertFalse(vendor.is_mapped("pre-swarm", "swarm"))

    def test_unmapped_rule(self):
        texts = {"a.md": "Use /swarm and the teach skill.", "b.md": "Run `tdd` then `bro`.", "c.md": "nothing here"}
        nv = {"pstack": ["swarm", "teach", "tdd", "bro", "unused"], "mattpocock": ["tdd", "other"]}
        router = "Routes: swarm goes to subagents. `tdd` is installed."
        found = vendor.analyse_mentions(texts, nv, router)
        by = {f["name"]: f for f in found}
        self.assertEqual(sorted(by), ["bro", "swarm", "tdd", "teach"])
        self.assertTrue(by["swarm"]["mapped"])
        self.assertTrue(by["tdd"]["mapped"])
        self.assertFalse(by["teach"]["mapped"])
        self.assertFalse(by["bro"]["mapped"])
        self.assertEqual(by["tdd"]["sources"], ["mattpocock", "pstack"])
        self.assertEqual(by["teach"]["files"], ["a.md"])

    def test_real_tree_has_no_unmapped_names(self):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "vendor.py"), "refs"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"refs: \d+ mentioned, \d+ mapped, 0 UNMAPPED", r.stdout)


def make_tar(files, top="repo-abc"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for path, data in files.items():
            info = tarfile.TarInfo(f"{top}/{path}")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r:gz")


class UpstreamInfoTests(unittest.TestCase):
    def setUp(self):
        self.tar = make_tar({
            "pstack/plugin.json": b'{"version": "0.15.21"}',
            "pstack/skills/how/SKILL.md": b"x",
            "pstack/skills/how/references/a.md": b"x",
            "pstack/skills/swarm/SKILL.md": b"x",
            "pstack/skills/notes/readme.md": b"x",
            "skills/eng/tdd/SKILL.md": b"x",
            "skills/eng/tdd/agents/SKILL.md": b"deeper",
            "skills/prod/grilling/SKILL.md": b"x",
        })
        self.index = vendor._index(self.tar)

    def test_detect_version(self):
        src = {"version_files": ["missing.json", "pstack/plugin.json"]}
        self.assertEqual(vendor.detect_version(src, self.tar, self.index), "0.15.21")
        src["version_prefix"] = "v"
        self.assertEqual(vendor.detect_version(src, self.tar, self.index), "v0.15.21")

    def test_detect_version_falls_back_to_unversioned(self):
        self.assertEqual(vendor.detect_version({"version_files": ["nope.json"]}, self.tar, self.index), "unversioned")
        self.assertEqual(vendor.detect_version({}, self.tar, self.index), "unversioned")
        tar = make_tar({"p.json": b"not json"})
        self.assertEqual(vendor.detect_version({"version_files": ["p.json"]}, tar, vendor._index(tar)), "unversioned")

    def test_upstream_and_vendored_skill_names(self):
        ps = {"skills_root": "pstack/skills", "skills_depth": 1}
        mp = {"skills_root": "skills", "skills_depth": 2}
        self.assertEqual(vendor.upstream_skill_names(ps, self.index), ["how", "swarm"])
        self.assertEqual(vendor.upstream_skill_names(mp, self.index), ["grilling", "tdd"])
        dests = ["plugins/proof/skills/tdd/SKILL.md", "plugins/proof/skills/tdd/agents/x.yaml", "other/y"]
        self.assertEqual(vendor.vendored_skill_names({"skills_dest": "plugins/proof/skills"}, dests), ["tdd"])


class ResolveCommitTests(unittest.TestCase):
    SHA = "a" * 40

    def fake_response(self, payload):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        return resp

    def test_uses_urllib_and_sends_token(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            return self.fake_response({"sha": self.SHA})

        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "tok"}), \
                mock.patch.object(vendor.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(vendor.resolve_commit("o/r"), self.SHA)
        self.assertEqual(seen["url"], "https://api.github.com/repos/o/r/commits/HEAD")
        self.assertEqual(seen["auth"], "Bearer tok")

    def test_falls_back_to_gh_when_urllib_fails(self):
        done = mock.Mock(returncode=0, stdout=json.dumps({"sha": self.SHA}).encode(), stderr=b"")
        with mock.patch.object(vendor.urllib.request, "urlopen", side_effect=OSError("offline")), \
                mock.patch.object(vendor.subprocess, "run", return_value=done) as run, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(vendor.resolve_commit("o/r", "abc123"), self.SHA)
        self.assertEqual(run.call_args[0][0], ["gh", "api", "repos/o/r/commits/abc123"])

    def test_error_when_both_fail_or_answer_is_odd(self):
        failed = mock.Mock(returncode=1, stdout=b"", stderr=b"no")
        with mock.patch.object(vendor.urllib.request, "urlopen", side_effect=OSError("offline")), \
                mock.patch.object(vendor.subprocess, "run", return_value=failed), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(vendor.VendorError):
                vendor.resolve_commit("o/r")
        with mock.patch.object(vendor.urllib.request, "urlopen",
                               return_value=self.fake_response({"sha": "short"})):
            with self.assertRaises(vendor.VendorError):
                vendor.resolve_commit("o/r")


class TrackTests(unittest.TestCase):
    SHA = "c" * 40

    def api(self, routes):
        calls = []

        def fake(path):
            calls.append(path)
            if path not in routes:
                raise AssertionError(f"unexpected API path {path}")
            return routes[path]
        return fake, calls

    def test_release_follows_latest_release_tag_to_its_commit(self):
        fake, calls = self.api({"repos/o/r/releases/latest": {"tag_name": "v1.3.1", "prerelease": False},
                                "repos/o/r/commits/v1.3.1": {"sha": self.SHA}})
        with mock.patch.object(vendor, "_api_json", fake):
            got = vendor.resolve_target({"repo": "o/r", "track": {"type": "release"}})
        self.assertEqual(got, (self.SHA, "release v1.3.1", "release v1.3.1"))
        self.assertEqual(calls, ["repos/o/r/releases/latest", "repos/o/r/commits/v1.3.1"])

    def test_release_refuses_prerelease_draft_or_missing_tag(self):
        for payload in ({"tag_name": "v2", "prerelease": True}, {"tag_name": "v2", "draft": True}, {}):
            fake, _ = self.api({"repos/o/r/releases/latest": payload})
            with self.subTest(payload=payload), mock.patch.object(vendor, "_api_json", fake):
                with self.assertRaises(vendor.VendorError):
                    vendor.resolve_target({"repo": "o/r", "track": {"type": "release"}})

    def test_path_follows_latest_commit_touching_the_path(self):
        fake, calls = self.api({"repos/o/r/commits?path=pstack/plugin.json&per_page=1": [{"sha": self.SHA}]})
        with mock.patch.object(vendor, "_api_json", fake):
            got = vendor.resolve_target({"repo": "o/r", "track": {"type": "path", "path": "pstack/plugin.json"}})
        self.assertEqual(got, (self.SHA, "path pstack/plugin.json", "commit ccccccc"))

    def test_path_with_no_commit_is_an_error(self):
        fake, _ = self.api({"repos/o/r/commits?path=x.json&per_page=1": []})
        with mock.patch.object(vendor, "_api_json", fake), self.assertRaises(vendor.VendorError):
            vendor.resolve_target({"repo": "o/r", "track": {"type": "path", "path": "x.json"}})

    def test_branch_follows_the_default_branch_tip(self):
        fake, _ = self.api({"repos/o/r/commits/HEAD": {"sha": self.SHA}})
        with mock.patch.object(vendor, "_api_json", fake):
            self.assertEqual(vendor.resolve_target({"repo": "o/r", "track": {"type": "branch"}}),
                             (self.SHA, "branch", "commit ccccccc"))

    def test_to_overrides_track(self):
        fake, calls = self.api({"repos/o/r/commits/abc123": {"sha": self.SHA}})
        with mock.patch.object(vendor, "_api_json", fake):
            got = vendor.resolve_target({"repo": "o/r", "track": {"type": "release"}}, "abc123")
        self.assertEqual(got, (self.SHA, "pinned by --to", "ccccccc"))
        self.assertEqual(calls, ["repos/o/r/commits/abc123"])

    def test_path_query_goes_to_the_api_url(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            resp = mock.MagicMock()
            resp.read.return_value = json.dumps([{"sha": self.SHA}]).encode()
            resp.__enter__.return_value = resp
            return resp
        with mock.patch.object(vendor.urllib.request, "urlopen", fake_urlopen):
            vendor.latest_path_commit("o/r", "pstack/plugin.json")
        self.assertEqual(seen["url"], "https://api.github.com/repos/o/r/commits?path=pstack/plugin.json&per_page=1")

    def test_compare_status(self):
        fake, calls = self.api({"repos/o/r/compare/aaa...bbb?per_page=1": {"status": "ahead"}})
        with mock.patch.object(vendor, "_api_json", fake):
            self.assertEqual(vendor.compare_status("o/r", "aaa", "bbb"), "ahead")
        fake, _ = self.api({"repos/o/r/compare/aaa...bbb?per_page=1": {"status": "weird"}})
        with mock.patch.object(vendor, "_api_json", fake), self.assertRaises(vendor.VendorError):
            vendor.compare_status("o/r", "aaa", "bbb")

    def test_labelled_version(self):
        rel = {"track": {"type": "release"}}
        path = {"track": {"type": "path", "path": "p.json"}}
        self.assertEqual(vendor.labelled_version(rel, "v1.3.1", "4" * 40, "5" * 40), "v1.3.1+4444444")
        self.assertEqual(vendor.labelled_version(rel, "v1.3.1", "5" * 40, "5" * 40), "v1.3.1")
        self.assertEqual(vendor.labelled_version(rel, "v1.3.1", "4" * 40, None), "v1.3.1")
        self.assertEqual(vendor.labelled_version(path, "0.15.20", "4" * 40, "5" * 40), "0.15.20")

    def test_version_matches_allows_the_sha_suffix(self):
        self.assertTrue(vendor.version_matches("v1.3.1", "v1.3.1"))
        self.assertTrue(vendor.version_matches("v1.3.1+4444444", "v1.3.1"))
        self.assertFalse(vendor.version_matches("v1.3.10", "v1.3.1"))
        self.assertFalse(vendor.version_matches("v1.3.2", "v1.3.1"))

    def test_download_without_gh_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(vendor, "CACHE", Path(tmp)), \
                mock.patch.object(vendor.urllib.request, "urlopen", side_effect=OSError("offline")), \
                mock.patch.object(vendor.subprocess, "run", side_effect=FileNotFoundError("gh")), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(vendor.VendorError) as cm:
                vendor._download({"repo": "o/r", "sha": "a" * 40})
        self.assertIn("gh unavailable", str(cm.exception))

    def test_load_config_validates_track(self):
        base = json.loads((ROOT / "vendor.json").read_text(encoding="utf-8"))
        for bad in (None, {"type": "tip"}, {"type": "path"}):
            cfg = json.loads(json.dumps(base))
            if bad is None:
                del cfg["sources"]["pstack"]["track"]
            else:
                cfg["sources"]["pstack"]["track"] = bad
            with self.subTest(track=bad), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "vendor.json"
                path.write_text(json.dumps(cfg), encoding="utf-8")
                with mock.patch.object(vendor, "CONFIG", path), self.assertRaises(vendor.VendorError):
                    vendor.load_config()

    def test_real_config_tracks(self):
        cfg = json.loads((ROOT / "vendor.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["sources"]["mattpocock"]["track"], {"type": "release"})
        self.assertEqual(cfg["sources"]["pstack"]["track"], {"type": "path", "path": "pstack/plugin.json"})


class UpdateFlowTests(unittest.TestCase):
    """Run cmd_update in a temp repo with fake upstream data."""
    OLD = "1" * 40
    NEW = "2" * 40

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cfg = {
            "sources": {"pstack": {
                "repo": "o/r", "sha": self.OLD, "version": "1.0.0", "label": "pstack", "license": "MIT",
                "license_file": "plugins/proof/LICENSES/pstack.txt", "track": {"type": "branch"}, "skills_root": "pstack/skills",
                "skills_depth": 1, "skills_dest": f"{P}/skills"}},
            "managed_roots": ["plugins/proof/references", "plugins/proof/LICENSES"],
            "rules": [{"source": "pstack", "type": "dir", "from": "pstack/skills/how", "to": f"{P}/skills/how"}],
        }
        (self.root / "vendor.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        (self.root / "plugins/proof/skills/work").mkdir(parents=True)
        (self.root / "plugins/proof/skills/work/SKILL.md").write_text("Router mentions swarm.\n", encoding="utf-8")
        self.sources = {self.OLD: {f"{P}/skills/how/SKILL.md": b"how v1\n", f"{P}/skills/how/gone.md": b"gone\n"},
                        self.NEW: {f"{P}/skills/how/SKILL.md": b"how v2 /swarm\n", f"{P}/skills/how/new.md": b"new\n"}}
        self.fake_version = "1.1.0"
        patches = [mock.patch.object(vendor, n, self.root / rel) for n, rel in (
            ("ROOT", "."), ("CONFIG", "vendor.json"), ("LOCK", "vendor.lock.json"),
            ("NOTICE", "plugins/proof/NOTICE.md"), ("CHANGELOG", "CHANGELOG.md"),
            ("PATCH", "_scratch/vendor-update.patch"), ("ROUTER", "plugins/proof/skills/work/SKILL.md"))]
        self.compare = "ahead"
        self.compare_calls = []
        patches += [mock.patch.object(vendor, "compare_status", self.fake_compare),
                    mock.patch.object(vendor, "build_plan", self.fake_build_plan),
                    mock.patch.object(vendor, "resolve_commit", lambda repo, ref="HEAD": self.latest)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.latest = self.OLD
        self.run_sync()

    def fake_build_plan(self, cfg):
        sha = cfg["sources"]["pstack"]["sha"]
        files = {d: {"source": "pstack", "upstream": "u/" + d, "dest": d, "sha256": hashlib.sha256(b).hexdigest(),
                     "size": len(b), "data": b} for d, b in self.sources[sha].items()}
        version = "1.0.0" if sha == self.OLD else self.fake_version
        return {"files": files, "upstream": {"pstack": ["how", "swarm", "teach"]}, "versions": {"pstack": version},
                "not_vendored": {"pstack": ["swarm", "teach"]}}

    def fake_compare(self, repo, base, head):
        self.compare_calls.append((repo, base, head))
        return self.compare

    def run_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vendor.cmd_sync(), 0)

    def update(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vendor.cmd_update(kw.get("sources"), kw.get("to"), kw.get("dry_run", False))
        return rc, buf.getvalue()

    def test_up_to_date(self):
        rc, out = self.update(dry_run=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[-1], "RESULT: up-to-date")
        self.assertFalse((self.root / "_scratch" / "vendor-update.patch").exists())

    def test_dry_run_writes_only_the_patch(self):
        self.latest = self.NEW
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        rc, out = self.update(dry_run=True)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        patch = after.pop(Path("_scratch/vendor-update.patch")).decode()
        self.assertEqual(after, before)
        self.assertIn("-how v1", patch)
        self.assertIn("+how v2 /swarm", patch)
        self.assertEqual(rc, 0)
        self.assertIn("pstack: 1.0.0 -> 1.1.0  (1111111 -> 2222222)", out)
        self.assertIn("files: 1 changed, 1 added, 1 removed", out)
        self.assertEqual(out.splitlines()[-1], "RESULT: updated")
        self.assertIn("  track: branch\n", out)

    def test_real_update_moves_pin_lock_and_changelog(self):
        self.latest = self.NEW
        rc, out = self.update()
        self.assertEqual(rc, 0, out)
        cfg = json.loads((self.root / "vendor.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["sources"]["pstack"]["sha"], cfg["sources"]["pstack"]["version"]), (self.NEW, "1.1.0"))
        lock = json.loads((self.root / "vendor.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["sources"]["pstack"]["sha"], self.NEW)
        self.assertEqual(sorted(e["dest"] for e in lock["files"]), [f"{P}/skills/how/SKILL.md", f"{P}/skills/how/new.md"])
        self.assertFalse((self.root / P / "skills/how/gone.md").exists())
        self.assertEqual((self.root / P / "skills/how/SKILL.md").read_bytes(), b"how v2 /swarm\n")
        log = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]\n\n### Changed\n\n- Upstream pstack 1.0.0 → 1.1.0 "
                      "(`1111111` → `2222222`): 1 changed, 1 added, 1 removed files.\n", log)
        self.assertEqual(out.splitlines()[-1], "RESULT: updated")

    def test_new_commit_with_no_vendored_change_keeps_the_old_pin(self):
        self.sources[self.NEW] = dict(self.sources[self.OLD])
        self.latest = self.NEW
        self.fake_version = "1.0.0"
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for dry in (True, False):
            rc, out = self.update(dry_run=dry)
            self.assertEqual(rc, 0, out)
            self.assertIn("pstack: up to date (no vendored change at 2222222)", out)
            self.assertEqual(out.splitlines()[-1], "RESULT: up-to-date")
            after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_same_files_but_new_version_is_an_update(self):
        self.sources[self.NEW] = dict(self.sources[self.OLD])
        self.latest = self.NEW
        self.fake_version = "1.0.1"
        rc, out = self.update(dry_run=True)
        self.assertIn("pstack: 1.0.0 -> 1.0.1", out)
        self.assertEqual(out.splitlines()[-1], "RESULT: updated")

    def test_unmapped_name_gives_exit_3(self):
        self.sources[self.NEW][f"{P}/skills/how/new.md"] = b"run the teach skill\n"
        self.latest = self.NEW
        rc, out = self.update(dry_run=True)
        self.assertEqual(rc, 3)
        self.assertEqual(out.splitlines()[-1], "RESULT: updated, action needed")
        self.assertIn("teach", out)

    def test_pin_ahead_of_or_diverged_from_the_target_is_kept(self):
        self.latest = self.NEW
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for status in ("behind", "diverged"):
            self.compare = status
            for dry in (True, False):
                with self.subTest(status=status, dry=dry):
                    rc, out = self.update(dry_run=dry)
                    self.assertEqual(rc, 0, out)
                    self.assertIn("pstack: kept pin 1111111: it is ahead of (or diverged from) "
                                  "the latest commit 2222222", out)
                    self.assertEqual(out.splitlines()[-1], "RESULT: up-to-date")
                    after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
                    self.assertEqual(after, before)
        self.assertEqual(self.compare_calls[0], ("o/r", self.OLD, self.NEW))

    def test_to_pins_exactly_and_skips_the_compare(self):
        self.latest = self.NEW
        self.compare = "behind"
        rc, out = self.update(sources=["pstack"], to=self.NEW, dry_run=True)
        self.assertEqual(self.compare_calls, [])
        self.assertIn("track: pinned by --to", out)
        self.assertEqual(out.splitlines()[-1], "RESULT: updated")

    def test_disagreeing_config_and_lock_stop_update_and_refs(self):
        raw = json.loads((self.root / "vendor.json").read_text(encoding="utf-8"))
        raw["sources"]["pstack"]["sha"] = self.NEW
        (self.root / "vendor.json").write_text(json.dumps(raw), encoding="utf-8")
        self.latest = self.NEW
        for call in (lambda: self.update(), lambda: vendor.cmd_refs()):
            with self.assertRaises(vendor.VendorError) as cm:
                call()
            self.assertEqual(str(cm.exception), "vendor.json and vendor.lock.json disagree for pstack; "
                                                "run python -I tools/vendor.py sync")

    def test_failed_sync_leaves_vendor_json_and_changelog_alone(self):
        self.latest = self.NEW
        cfg_before = (self.root / "vendor.json").read_bytes()
        with mock.patch.object(vendor, "cmd_sync", side_effect=vendor.VendorError("disk full")):
            with self.assertRaises(vendor.VendorError):
                self.update()
        self.assertEqual((self.root / "vendor.json").read_bytes(), cfg_before)
        self.assertFalse((self.root / "CHANGELOG.md").exists())

    def test_release_track_labels_code_that_is_not_the_release(self):
        raw = json.loads((self.root / "vendor.json").read_text(encoding="utf-8"))
        raw["sources"]["pstack"]["track"] = {"type": "release"}
        (self.root / "vendor.json").write_text(json.dumps(raw), encoding="utf-8")
        release_sha = "3" * 40

        def fake_target(src, to=None):
            return (self.NEW, "pinned by --to", "2222222") if to else (release_sha, "release v9", "release v9")
        with mock.patch.object(vendor, "resolve_target", fake_target):
            rc, out = self.update(sources=["pstack"], to=self.NEW)
        self.assertIn("pstack: 1.0.0 -> 1.1.0+2222222", out)
        cfg = json.loads((self.root / "vendor.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["sources"]["pstack"]["version"], "1.1.0+2222222")
        self.assertIn("1.0.0 \u2192 1.1.0+2222222", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_to_needs_exactly_one_source(self):
        with self.assertRaises(vendor.VendorError):
            self.update(to=self.NEW)
        with self.assertRaises(vendor.VendorError):
            self.update(sources=["nope"])

    def test_lock_records_not_vendored(self):
        lock = json.loads((self.root / "vendor.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["not_vendored"], {"pstack": ["swarm", "teach"]})


if __name__ == "__main__":
    unittest.main()

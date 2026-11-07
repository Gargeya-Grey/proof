"""Tests for tools/doctor.py. Each test builds a fake home folder; none reads the real one."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from toolload import load

doctor = load("doctor")

ROUTER = "# Work\n\nroute A\n"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def plugin(root, text=ROUTER):
    write(Path(root) / "skills" / "work" / "SKILL.md", text)
    return Path(root)


def transcript(home, name, base, age=0, stamp=None, extra=""):
    """A transcript line as Claude Code writes it: JSON with the base directory escaped."""
    entry = {"type": "user", "message": {"content": [
        {"type": "text", "text": f"Base directory for this skill: {base}\n\n# Work"}]}}
    if stamp:
        entry["timestamp"] = stamp
    line = json.dumps(entry) + ("\n" + extra if extra else "")
    p = Path(home) / ".claude" / "projects" / "proj" / f"{name}.jsonl"
    write(p, line + "\n")
    t = time.time() - age
    os.utime(p, (t, t))
    return p


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        plugin(self.repo / "plugins" / "proof")
        self.home = self.base / "home"

    def run_report(self):
        return doctor.report(self.home, self.repo)

    def test_names_the_copy_from_the_transcript_not_from_the_cache(self):
        live = plugin(self.base / "clone" / "plugins" / "proof")
        plugin(self.home / ".claude" / "plugins" / "cache" / "m" / "proof" / "0.1.0", "# Work\n\nold\n")
        transcript(self.home, "s1", str(live / "skills" / "work"))
        lines, code = self.run_report()
        self.assertIn(f"claude: loads {live}", lines[0])
        self.assertIn("same as this repository", lines[0])
        self.assertNotIn("cache", lines[0])

    def test_newest_transcript_wins(self):
        old = plugin(self.base / "old" / "plugins" / "proof", "# Work\n\nold\n")
        new = plugin(self.base / "new" / "plugins" / "proof")
        transcript(self.home, "a", str(old / "skills" / "work"), age=100)
        transcript(self.home, "b", str(new / "skills" / "work"))
        self.assertIn(str(new), self.run_report()[0][0])

    def test_a_different_router_fails_with_the_fix(self):
        other = plugin(self.base / "gh" / "plugins" / "proof", "# Work\n\nold\n")
        transcript(self.home, "s1", str(other / "skills" / "work"))
        lines, code = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("DIFFERS", lines[0])
        self.assertIn("claude plugin update", lines[0])

    def test_windows_escaped_path_is_read(self):
        live = plugin(self.base / "win" / "plugins" / "proof")
        transcript(self.home, "s1", str(live / "skills" / "work").replace("/", "\\"))
        self.assertIn("same as this repository", self.run_report()[0][0])

    def test_codex_newest_version_is_compared(self):
        plugin(self.home / ".codex" / "plugins" / "cache" / "m" / "proof" / "0.5.0", "# Work\n\nold\n")
        plugin(self.home / ".codex" / "plugins" / "cache" / "m" / "proof" / "0.10.0")
        lines, _ = self.run_report()
        codex = next(l for l in lines if l.startswith("codex:"))
        self.assertIn("0.10.0", codex)
        self.assertIn("same as this repository", codex)

    def test_codex_stale_copy_fails(self):
        plugin(self.home / ".codex" / "plugins" / "cache" / "m" / "proof" / "0.6.0", "# Work\n\nold\n")
        lines, code = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("codex plugin add", next(l for l in lines if l.startswith("codex:")))

    def test_nothing_installed_is_reported_not_failed(self):
        lines, code = self.run_report()
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("claude: no proof router load found"))
        self.assertTrue(any(l.startswith("codex: no installed and enabled proof copy") for l in lines))

    def test_crlf_router_counts_as_the_same(self):
        live = plugin(self.base / "crlf" / "plugins" / "proof")
        (live / "skills" / "work" / "SKILL.md").write_bytes(ROUTER.replace("\n", "\r\n").encode("utf-8"))
        transcript(self.home, "s1", str(live / "skills" / "work"))
        self.assertIn("same as this repository", self.run_report()[0][0])


    def test_the_latest_load_event_wins_over_the_latest_written_file(self):
        old = plugin(self.base / "old2" / "plugins" / "proof", "# Work\n\nold\n")
        new = plugin(self.base / "new2" / "plugins" / "proof")
        # The old session loaded first but wrote its transcript last (it is still running).
        transcript(self.home, "still-running", str(old / "skills" / "work"), age=0,
                   stamp="2026-11-01T10:00:00.000Z", extra='{"type": "assistant"}')
        transcript(self.home, "newer-load", str(new / "skills" / "work"), age=100,
                   stamp="2026-11-07T10:00:00.000Z")
        self.assertIn(str(new), self.run_report()[0][0])

    def test_unc_path_keeps_its_prefix(self):
        self.assertEqual(doctor._clean(r"\\\\server\\share\\proof\\skills\\work"),
                         "//server/share/proof/skills/work")
        self.assertEqual(doctor._clean(r"C:\\x\\\\y"), "C:/x/y")

    def codex_config(self, text):
        write(self.home / ".codex" / "config.toml", text)

    def test_codex_disabled_plugin_is_not_reported_as_running(self):
        plugin(self.home / ".codex" / "plugins" / "cache" / "m" / "proof" / "0.6.0", "# Work\n\nold\n")
        self.codex_config('[plugins."proof@m"]\nenabled = false\n')
        lines, code = self.run_report()
        self.assertEqual(code, 0)
        self.assertTrue(any(l.startswith("codex: no installed and enabled proof copy") for l in lines))

    def test_codex_enabled_marketplace_is_chosen(self):
        plugin(self.home / ".codex" / "plugins" / "cache" / "a" / "proof" / "0.9.0", "# Work\n\nold\n")
        plugin(self.home / ".codex" / "plugins" / "cache" / "b" / "proof" / "0.1.0")
        self.codex_config('[plugins."proof@b"]\nenabled = true\n')
        codex = next(l for l in self.run_report()[0] if l.startswith("codex:"))
        self.assertIn(str(Path("b") / "proof" / "0.1.0"), codex)
        self.assertIn("same as this repository", codex)

    def test_codex_local_and_numeric_folders_compare(self):
        plugin(self.home / ".codex" / "plugins" / "cache" / "m" / "proof" / "local", "# Work\n\nold\n")
        plugin(self.home / ".codex" / "plugins" / "cache" / "m" / "proof" / "0.7.0")
        codex = next(l for l in self.run_report()[0] if l.startswith("codex:"))
        self.assertIn("0.7.0", codex)
        self.assertIn("2 version folders", codex)


if __name__ == "__main__":
    unittest.main()

"""Tests for plugins/proof/hooks/proof_hook.py and hooks.json.

Each test runs the script as a subprocess with sample JSON in the input shapes of Claude Code and
Codex, and with its own temp folder (TMPDIR, TEMP and TMP point at it), so the real temp markers
are never touched.

Run: python -I -m unittest discover -s tests -p test_hooks.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "proof"
HOOKS_DIR = PLUGIN / "hooks"
SCRIPT = HOOKS_DIR / "proof_hook.py"
HUB = PLUGIN / "references" / "pstack" / "skills" / "poteto-mode" / "SKILL.md"
HUB_REL = "references/pstack/skills/poteto-mode/SKILL.md"

CONTEXT_CAP = 2000
MESSAGE_CAP = 400
DENY_CAP = 1000
PRECOMPACT_CAP = 4000  # the script's own cap; the host cap is 10,000 characters

SID = "11111111-2222-4333-8444-555555555555"

# Input shapes. Claude Code sends prompt_id; Codex sends turn_id and model (hooks docs).
CLAUDE = {"transcript_path": "C:\\x\\t.jsonl", "cwd": "C:\\work", "permission_mode": "default"}
CODEX = {"transcript_path": "C:\\x\\r.jsonl", "cwd": "C:\\work", "turn_id": "t1", "model": "gpt-x"}


def payload(shape, event, **fields):
    data = dict(shape)
    data.update({"session_id": SID, "hook_event_name": event})
    data.update(fields)
    return data


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="proof-hook-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.temp_dir = self.tmp / "temp"
        self.temp_dir.mkdir()
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()

    def env(self, temp=None):
        env = dict(os.environ)
        for name in ("TMPDIR", "TEMP", "TMP"):
            env[name] = str(temp if temp is not None else self.temp_dir)
        return env

    def proof_transcript(self, text=None):
        """A transcript that shows proof in use: the router load line as Claude Code writes it."""
        path = self.tmp / "transcript.jsonl"
        if text is None:
            text = json.dumps({"type": "user", "isMeta": True, "message": {"content": [{"type": "text",
                   "text": "Base directory for this skill: %s" % (PLUGIN / "skills" / "work")}]}})
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def run_hook(self, sub, data=None, raw=None, temp=None, script=SCRIPT):
        if isinstance(data, dict) and data.get("transcript_path") in (CLAUDE["transcript_path"], CODEX["transcript_path"]):
            # The sample shapes name a transcript that does not exist: give them one that shows proof in use.
            if not (self.tmp / "transcript.jsonl").exists():
                self.proof_transcript()
            data = dict(data, transcript_path=str(self.tmp / "transcript.jsonl"))
        if raw is None:
            raw = json.dumps(data).encode("utf-8") if data is not None else b""
        done = subprocess.run(
            [sys.executable, "-I", str(script), sub],
            input=raw,
            capture_output=True,
            env=self.env(temp),
            cwd=str(self.cwd),
            timeout=60,
        )
        return done.returncode, done.stdout.decode("utf-8"), done.stderr.decode("utf-8")

    def marker(self, session_id=SID):
        return self.temp_dir / "proof-hooks" / (session_id + ".json")

    def compact(self, shape=CLAUDE, session_id=SID):
        rc, out, _ = self.run_hook("session-start", payload(shape, "SessionStart", source="compact", session_id=session_id))
        self.assertEqual(rc, 0)
        self.assertTrue(self.marker(session_id).exists(), "compact must write a marker")
        return out

    def gate(self, tool="Edit", shape=CLAUDE, **extra):
        tool_input = {"file_path": "C:\\work\\a.py"} if tool != "apply_patch" else {"command": "*** Begin Patch\n*** End Patch"}
        data = payload(shape, "PreToolUse", tool_name=tool, tool_input=tool_input, tool_use_id="u1", **extra)
        rc, out, err = self.run_hook("gate", data)
        self.assertEqual(rc, 0, err)
        return out

    def assertDenied(self, out):
        self.assertTrue(out.strip(), "expected a deny, got no output")
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "PreToolUse")
        self.assertEqual(body["permissionDecision"], "deny")
        reason = body["permissionDecisionReason"]
        self.assertTrue(reason.startswith("proof:"), reason)
        self.assertIn(str(HUB), reason)
        self.assertLessEqual(len(reason), DENY_CAP)

    def assertAllowed(self, out):
        self.assertEqual(out.strip(), "", "expected no output (allow), got: " + out)

    def release(self, tool, tool_input, shape=CLAUDE, response=None, **extra):
        data = payload(shape, "PostToolUse", tool_name=tool, tool_input=tool_input, tool_use_id="u2", **extra)
        if response is not None:
            data["tool_response"] = response
        rc, out, err = self.run_hook("release", data)
        self.assertEqual(rc, 0, err)
        return out


class PreCompactTests(HookCase):
    def test_01_precompact_asks_for_the_active_proof_files_section(self):
        for shape in (CLAUDE, CODEX):
            for trigger in ("manual", "auto"):
                with self.subTest(shape=shape is CODEX, trigger=trigger):
                    data = payload(shape, "PreCompact", trigger=trigger, custom_instructions=None)
                    rc, out, err = self.run_hook("precompact", data)
                    self.assertEqual(rc, 0, err)
                    self.assertTrue(out.startswith("proof:"))
                    self.assertIn('"Active proof files"', out)
                    self.assertIn("absolute path", out)
                    self.assertIn("playbook step", out)
                    self.assertIn(str(PLUGIN / "skills" / "work" / "SKILL.md"), out)
                    self.assertLessEqual(len(out), PRECOMPACT_CAP)

    def test_02_precompact_prints_even_with_no_input(self):
        rc, out, _ = self.run_hook("precompact", raw=b"")
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("proof:"))


class SessionStartTests(HookCase):
    def check_context(self, out):
        body = json.loads(out)
        context = body["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertTrue(context.startswith("proof:"))
        self.assertLessEqual(len(context), CONTEXT_CAP)
        self.assertIn("Skill `proof:work`", context)
        self.assertIn(str(HUB), context)
        self.assertIn("Active proof files", context)
        self.assertIn("AGENTS.md", context)
        self.assertIn("CLAUDE.md", context)
        # the order: skill, then hub, then summary files, then instruction files
        order = [context.index(s) for s in ("`work` skill again", str(HUB), "Active proof files", "AGENTS.md")]
        self.assertEqual(order, sorted(order))
        message = body["systemMessage"]
        self.assertTrue(message.startswith("proof:"))
        self.assertLessEqual(len(message), MESSAGE_CAP)
        self.assertNotIn("NOT active", message)

    def test_03_compact_writes_marker_and_injects_context(self):
        for shape in (CLAUDE, CODEX):
            with self.subTest(codex=shape is CODEX):
                out = self.compact(shape)
                self.check_context(out)
                body = json.loads(self.marker().read_text(encoding="utf-8"))
                self.assertEqual(body["session_id"], SID)
                self.assertLess(abs(time.time() - body["created"]), 120)
                self.assertTrue(body["created_iso"].endswith("Z"))
                self.marker().unlink()

    def test_04_other_sources_do_nothing(self):
        for source in ("startup", "resume", "clear", "fork"):
            rc, out, _ = self.run_hook("session-start", payload(CLAUDE, "SessionStart", source=source))
            self.assertEqual(rc, 0)
            self.assertAllowed(out)
        self.assertFalse(self.marker().exists())

    def test_05_hub_path_comes_from_the_script_location(self):
        # Copy the script to another plugin root: the hub path in the context must follow it.
        other = self.tmp / "other-plugin"
        (other / "hooks").mkdir(parents=True)
        copy = other / "hooks" / "proof_hook.py"
        shutil.copy(str(SCRIPT), str(copy))
        rc, out, _ = self.run_hook("session-start", payload(CLAUDE, "SessionStart", source="compact"), script=copy)
        self.assertEqual(rc, 0)
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(str(other.resolve() / "references" / "pstack" / "skills" / "poteto-mode" / "SKILL.md"), context)

    def test_06_long_plugin_path_keeps_the_cap_and_the_prefix(self):
        deep = self.tmp
        for _ in range(4):
            deep = deep / ("d" * 40)
        try:
            (deep / "hooks").mkdir(parents=True)
            copy = deep / "hooks" / "proof_hook.py"
            shutil.copy(str(SCRIPT), str(copy))
        except OSError as exc:
            # A long temp folder can push this path past the Windows path limit (260 characters).
            self.skipTest("cannot create the long test path here: %s" % exc)
        rc, out, _ = self.run_hook("session-start", payload(CLAUDE, "SessionStart", source="compact"), script=copy)
        self.assertEqual(rc, 0)
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(context.startswith("proof:"))
        self.assertLessEqual(len(context), CONTEXT_CAP)


class GateTests(HookCase):
    def test_10_gate_denies_every_edit_tool_after_compact(self):
        self.compact()
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.assertDenied(self.gate(tool))

    def test_11_gate_denies_codex_edit_tools(self):
        self.compact(CODEX)
        for tool in ("apply_patch", "Edit", "Write"):
            with self.subTest(tool=tool):
                self.assertDenied(self.gate(tool, CODEX))

    def test_12_gate_ignores_tools_that_do_not_edit(self):
        self.compact()
        for tool in ("Read", "Grep", "Glob", "Agent"):
            with self.subTest(tool=tool):
                self.assertAllowed(self.gate(tool))

    def test_13_gate_allows_with_no_marker(self):
        self.assertAllowed(self.gate("Edit"))
        self.assertAllowed(self.gate("apply_patch", CODEX))

    def test_14_gate_allows_another_session(self):
        self.compact(session_id="other-session")
        self.assertAllowed(self.gate("Edit"))

    def test_15_gate_allows_a_subagent_call(self):
        self.compact()
        self.assertAllowed(self.gate("Edit", agent_id="a5027ed09365fead8", agent_type="builder"))
        self.assertAllowed(self.gate("apply_patch", CODEX, agent_id="agent-1"))
        self.assertDenied(self.gate("Edit"))  # the main agent is still gated

    def test_16_gate_allows_an_expired_marker(self):
        self.compact()
        body = json.loads(self.marker().read_text(encoding="utf-8"))
        body["created"] = time.time() - 24 * 3600 - 60
        self.marker().write_text(json.dumps(body), encoding="utf-8")
        self.assertAllowed(self.gate("Edit"))
        body["created"] = time.time() - 23 * 3600
        self.marker().write_text(json.dumps(body), encoding="utf-8")
        self.assertDenied(self.gate("Edit"))

    def test_17_gate_allows_a_corrupt_marker(self):
        self.compact()
        self.marker().write_text("{not json", encoding="utf-8")
        self.assertAllowed(self.gate("Edit"))


class ReleaseTests(HookCase):
    def test_20_gate_allows_after_a_read_of_the_hub(self):
        self.compact()
        self.assertDenied(self.gate("Edit"))
        self.release("Read", {"file_path": str(HUB)})
        self.assertFalse(self.marker().exists())
        self.assertAllowed(self.gate("Edit"))

    def test_21_read_with_forward_slashes_counts(self):
        self.compact()
        self.release("Read", {"file_path": str(HUB).replace("\\", "/")})
        self.assertFalse(self.marker().exists())

    def test_21b_a_partial_read_keeps_the_marker(self):
        self.compact()
        for tool_input in ({"offset": 40}, {"limit": 20}, {"offset": 1, "limit": 30}):
            with self.subTest(tool_input=tool_input):
                self.release("Read", dict(tool_input, file_path=str(HUB)))
                self.assertTrue(self.marker().exists())
        self.release("Read", {"file_path": str(HUB), "offset": 1, "limit": 2000})
        self.assertFalse(self.marker().exists())

    def test_22_gate_allows_after_a_shell_cat_of_the_hub(self):
        full = HUB.read_text(encoding="utf-8")
        fwd = str(HUB).replace("\\", "/")
        git_bash = "/" + fwd[0].lower() + fwd[2:] if fwd[1:2] == ":" else fwd
        cases = [
            ("Bash", CLAUDE, {"command": 'cat "%s"' % fwd}, {"stdout": full, "stderr": "", "interrupted": False}),
            ("Bash", CLAUDE, {"command": 'cat "%s"' % git_bash}, {"stdout": full, "stderr": ""}),
            ("PowerShell", CLAUDE, {"command": 'Get-Content -Raw "%s"' % HUB}, {"stdout": full, "stderr": ""}),
            ("exec_command", CODEX, {"cmd": "cat %s" % fwd}, {"output": full, "exit_code": 0}),
            ("shell", CODEX, {"command": ["bash", "-lc", "cat " + fwd]}, None),  # a shape with no text
        ]
        for tool, shape, tool_input, response in cases:
            with self.subTest(tool=tool, input=tool_input):
                self.compact(shape)
                self.assertDenied(self.gate("Edit", shape))
                self.release(tool, tool_input, shape, response=response)
                self.assertFalse(self.marker().exists())
                self.assertAllowed(self.gate("Edit", shape))

    def test_22b_a_read_that_shows_too_little_keeps_the_marker(self):
        full = HUB.read_text(encoding="utf-8")
        fwd = str(HUB).replace("\\", "/")
        cases = [
            ("Bash", {"command": "head -n 5 %s" % fwd}, {"stdout": "\n".join(full.splitlines()[:5]), "stderr": ""}),
            ("Bash", {"command": "test -f %s" % fwd}, {"stdout": "", "stderr": ""}),
            ("Bash", {"command": "cat %s" % fwd}, "cat: no such file"),
            ("Read", {"file_path": str(HUB)}, {"type": "text", "file": {"filePath": fwd, "content": full[:2000]}}),
        ]
        for tool, tool_input, response in cases:
            with self.subTest(tool=tool, input=tool_input):
                self.compact()
                self.release(tool, tool_input, response=response)
                self.assertTrue(self.marker().exists())
        self.release("Read", {"file_path": str(HUB)}, response={"type": "text", "file": {"filePath": fwd, "content": full}})
        self.assertFalse(self.marker().exists())

    def test_22c_a_hub_of_another_copy_keeps_the_marker(self):
        other = self.tmp / "cache" / "proof" / "0.6.0" / HUB_REL
        other.parent.mkdir(parents=True)
        shutil.copy(str(HUB), str(other))
        full = HUB.read_text(encoding="utf-8")
        self.compact()
        self.release("Read", {"file_path": str(other)}, response={"type": "text", "file": {"content": full}})
        self.release("Bash", {"command": "cat %s" % HUB_REL}, response={"stdout": full})
        self.assertTrue(self.marker().exists())

    def test_22d_shell_calls_wait_for_the_hub_too(self):
        self.compact()
        self.assertDenied(self.gate("Bash"))
        self.assertDenied(self.gate("exec_command", CODEX))
        data = payload(CLAUDE, "PreToolUse", tool_name="Bash", tool_input={"command": "cat '%s'" % HUB}, tool_use_id="u3")
        rc, out, _ = self.run_hook("gate", data)
        self.assertEqual(rc, 0)
        self.assertAllowed(out)

    def test_23_other_reads_and_commands_keep_the_marker(self):
        self.compact()
        self.release("Read", {"file_path": str(PLUGIN / "skills" / "work" / "SKILL.md")})
        self.release("Bash", {"command": "cat README.md"})
        self.release("Read", {"file_path": str(HUB.parent / "playbooks" / "feature.md")})
        self.assertTrue(self.marker().exists())
        self.assertDenied(self.gate("Edit"))

    def test_24_a_failed_shell_command_keeps_the_marker(self):
        self.compact()
        full = HUB.read_text(encoding="utf-8")
        command = {"command": "cat '%s'" % HUB}
        self.release("Bash", command, response={"exit_code": 1, "output": full})
        self.assertTrue(self.marker().exists())
        self.release("Bash", command, response={"exit_code": 0, "output": full})
        self.assertFalse(self.marker().exists())

    def test_25_a_subagent_read_keeps_the_marker(self):
        self.compact()
        self.release("Read", {"file_path": str(HUB)}, agent_id="a1", agent_type="builder")
        self.assertTrue(self.marker().exists())

    def test_26_a_tool_that_is_not_read_or_shell_keeps_the_marker(self):
        self.compact()
        self.release("Write", {"file_path": str(HUB), "content": "x"})
        self.assertTrue(self.marker().exists())

    def test_27_release_with_no_marker_is_quiet(self):
        out = self.release("Read", {"file_path": str(HUB)})
        self.assertAllowed(out)


class ProofInUseTests(HookCase):
    def test_60_a_session_without_proof_gets_no_notice_and_no_gate(self):
        self.proof_transcript(json.dumps({"type": "user", "message": {"content": "write my essay"}}))
        for sub, event in (("precompact", "PreCompact"), ("session-start", "SessionStart")):
            with self.subTest(sub=sub):
                rc, out, _ = self.run_hook(sub, payload(CLAUDE, event, source="compact", trigger="auto"))
                self.assertEqual((rc, out), (0, ""))
        self.assertFalse(self.marker().exists())
        self.assertAllowed(self.gate("Edit"))

    def test_61_actions_that_used_proof_count(self):
        def tool_use(name, tool_input):
            return json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t", "name": name, "input": tool_input}]}})
        signs = [
            json.dumps({"type": "user", "isMeta": True, "message": {"content": [{"type": "text", "text":
                "Base directory for this skill: C:\\u\\.claude\\plugins\\cache\\m\\proof\\0.6.0\\skills\\work\n\n# Work"}]}}),
            tool_use("Skill", {"skill": "proof:work"}),
            tool_use("Read", {"file_path": "/x/references/pstack/skills/poteto-mode/SKILL.md"}),
            json.dumps({"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                "arguments": json.dumps({"cmd": "cat /home/u/.codex/plugins/cache/m/proof/0.6.0/skills/work/SKILL.md"})}}),
            json.dumps({"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
                "input": "read('C:\\\\u\\\\proof\\\\skills\\\\work\\\\SKILL.md')"}}),
        ]
        for sign in signs:
            with self.subTest(sign=sign[:60]):
                self.proof_transcript(sign)
                self.compact()
                self.marker().unlink()

    def test_61b_text_that_only_mentions_proof_does_not_count(self):
        """Seen in a real probe (2026-11-07): the skill listing and CLAUDE.md name `proof:work` in
        every session, so they must not count as use."""
        mentions = [
            json.dumps({"type": "attachment", "attachment": {"type": "skill_listing",
                "content": "- proof:work: Verification-first routine"}}),
            json.dumps({"type": "attachment", "attachment": {"type": "instructions",
                "content": "| 1 | Load `proof:work`, write a 3-line plan |"}}),
            json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t",
                "content": "Base directory for this skill: /x/proof/skills/work"}]}}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text",
                "text": "Read references/pstack/skills/poteto-mode/SKILL.md next."}]}}),
            json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "see /c/proof/0.6.0/skills/work/SKILL.md"}]}}),
        ]
        self.proof_transcript("\n".join(mentions))
        rc, out, _ = self.run_hook("session-start", payload(CLAUDE, "SessionStart", source="compact"))
        self.assertEqual((rc, out), (0, ""))
        self.assertFalse(self.marker().exists())

    def test_62_no_transcript_sends_the_notice_without_a_gate(self):
        data = payload(CLAUDE, "SessionStart", source="compact")
        data["transcript_path"] = str(self.tmp / "missing.jsonl")
        rc, out, _ = self.run_hook("session-start", data)
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertIn("NOT active", body["systemMessage"])
        self.assertTrue(body["hookSpecificOutput"]["additionalContext"].startswith("proof:"))
        self.assertFalse(self.marker().exists())

    def test_63_a_chained_shell_command_that_names_the_hub_is_gated(self):
        self.compact()
        for command in ("cat '%s' && touch x" % HUB, "cat '%s'; rm a" % HUB, "cat '%s' > copy" % HUB,
                        "cat '%s' | tee b" % HUB, "echo $(cat '%s')" % HUB, "cat '%s'\ntouch x" % HUB):
            with self.subTest(command=command):
                data = payload(CLAUDE, "PreToolUse", tool_name="Bash", tool_input={"command": command}, tool_use_id="u4")
                rc, out, _ = self.run_hook("gate", data)
                self.assertEqual(rc, 0)
                self.assertDenied(out)


class FastPathTests(HookCase):
    def load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("proof_hook_under_test", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_54_an_expired_marker_keeps_the_fast_path(self):
        module = self.load_module()
        folder = self.temp_dir / "proof-hooks"
        folder.mkdir()
        old = folder / "abandoned.json"
        old.write_text("{}", encoding="utf-8")
        then = time.time() - 25 * 3600
        os.utime(str(old), (then, then))
        saved_argv, saved_env = sys.argv, {k: os.environ.get(k) for k in ("TMPDIR", "TEMP", "TMP")}
        try:
            sys.argv = ["proof_hook.py", "gate"]
            for name in ("TMPDIR", "TEMP", "TMP"):
                os.environ[name] = str(self.temp_dir)
            self.assertTrue(module.no_marker_at_all())
            fresh = folder / "live.json"
            fresh.write_text("{}", encoding="utf-8")
            self.assertFalse(module.no_marker_at_all())
        finally:
            sys.argv = saved_argv
            for name, value in saved_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_50_no_marker_folder_exits_at_once(self):
        for sub in ("gate", "release"):
            with self.subTest(sub=sub):
                rc, out, err = self.run_hook(sub, payload(CLAUDE, "PreToolUse", tool_name="Edit", tool_input={}))
                self.assertEqual((rc, out, err), (0, "", ""))
        self.assertFalse((self.temp_dir / "proof-hooks").exists())

    def test_51_an_empty_marker_folder_exits_at_once(self):
        self.compact()
        self.release("Read", {"file_path": str(HUB)})
        self.assertEqual(list((self.temp_dir / "proof-hooks").glob("*.json")), [])
        self.assertAllowed(self.gate("Edit"))

    def test_52_another_session_marker_takes_the_full_path(self):
        self.compact(session_id="other-session")
        self.assertAllowed(self.gate("Edit"))
        self.compact()
        self.assertDenied(self.gate("Edit"))

    def test_53_the_fast_path_loads_no_module_beyond_os_and_sys(self):
        src = SCRIPT.read_text(encoding="utf-8")
        head = src[: src.index("import json")]
        imports = [line.split()[1] for line in head.splitlines() if line.startswith("import ")]
        self.assertEqual(imports, ["os", "sys"])


class FailOpenTests(HookCase):
    SUBS = ("precompact", "session-start", "gate", "release")

    def test_30_bad_input_fails_open(self):
        self.compact()
        bad_inputs = [
            b"",
            b"not json",
            b"[1, 2]",
            b"null",
            b'{"session_id": 5}',
            b'{"hook_event_name": "PreToolUse", "tool_name": "Edit"}',
            b'{"session_id": "%s", "tool_name": ["Edit"]}' % SID.encode(),
            b"\xff\xfe\x00bad bytes",
        ]
        for sub in ("session-start", "gate", "release"):
            for raw in (bad_inputs if sub == "gate" else bad_inputs[:5]):
                with self.subTest(sub=sub, raw=raw[:30]):
                    rc, out, err = self.run_hook(sub, raw=raw)
                    self.assertEqual(rc, 0, err)
                    self.assertNotIn("deny", out)
                    if err:
                        self.assertTrue(err.startswith("proof:"), err)

    def test_30b_a_malformed_tool_input_still_gates_a_live_marker(self):
        # The session and the tool are valid, so the gate applies whatever tool_input holds.
        self.compact()
        raw = b'{"session_id": "%s", "tool_name": "Edit", "tool_input": 7}' % SID.encode()
        rc, out, err = self.run_hook("gate", raw=raw)
        self.assertEqual(rc, 0, err)
        self.assertDenied(out)

    def test_31_unknown_subcommand_fails_open(self):
        rc, out, err = self.run_hook("nope", payload(CLAUDE, "PreToolUse"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("proof:"), err)

    def test_32_unwritable_temp_folder_fails_open(self):
        blocker = self.tmp / "a-file-not-a-folder"
        blocker.write_text("x", encoding="utf-8")
        bad_values = [blocker, blocker / "below"]
        for bad in bad_values:
            with self.subTest(temp=str(bad)):
                rc, out, err = self.run_hook(
                    "session-start", payload(CLAUDE, "SessionStart", source="compact"), temp=bad
                )
                self.assertEqual(rc, 0, err)
                self.assertTrue(err.startswith("proof:"), err)
                body = json.loads(out)  # the reload notice still goes out
                self.assertTrue(body["hookSpecificOutput"]["additionalContext"].startswith("proof:"))
                self.assertIn("NOT active", body["systemMessage"])
                self.assertTrue(body["systemMessage"].startswith("proof:"))
                rc, out, err = self.run_hook(
                    "gate",
                    payload(CLAUDE, "PreToolUse", tool_name="Edit", tool_input={"file_path": "a"}),
                    temp=bad,
                )
                self.assertEqual(rc, 0, err)
                self.assertAllowed(out)
                rc, out, err = self.run_hook(
                    "release",
                    payload(CLAUDE, "PostToolUse", tool_name="Read", tool_input={"file_path": str(HUB)}),
                    temp=bad,
                )
                self.assertEqual(rc, 0, err)
        self.assertEqual(list(self.cwd.iterdir()), [], "no fallback write into the working folder")

    def test_33_marker_folder_is_the_only_thing_written(self):
        self.compact()
        self.assertEqual([p.name for p in self.temp_dir.iterdir()], ["proof-hooks"])
        self.assertEqual([p.name for p in (self.temp_dir / "proof-hooks").iterdir()], [SID + ".json"])
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_34_session_id_cannot_escape_the_marker_folder(self):
        rc, _, err = self.run_hook(
            "session-start", payload(CLAUDE, "SessionStart", source="compact", session_id="..\\..\\evil/../x")
        )
        self.assertEqual(rc, 0, err)
        files = [p for p in self.temp_dir.rglob("*") if p.is_file()]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].parent.name, "proof-hooks")

    def test_35_old_markers_are_swept(self):
        folder = self.temp_dir / "proof-hooks"
        folder.mkdir()
        old = folder / "old-session.json"
        old.write_text("{}", encoding="utf-8")
        past = time.time() - 3 * 24 * 3600
        os.utime(str(old), (past, past))
        self.compact()
        self.assertFalse(old.exists())


class HooksJsonTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))

    def test_40_hooks_json_has_the_wrapper_and_the_four_events(self):
        self.assertIn("hooks", self.config)
        events = self.config["hooks"]
        self.assertEqual(sorted(events), ["PostToolUse", "PreCompact", "PreToolUse", "SessionStart"])
        matchers = {name: groups[0]["matcher"] for name, groups in events.items()}
        self.assertEqual(matchers["PreCompact"], "manual|auto")
        self.assertEqual(matchers["SessionStart"], "compact")
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"):
            self.assertIn(tool, matchers["PreToolUse"].split("|"))
        for tool in ("Read", "Bash", "PowerShell", "exec_command"):
            self.assertIn(tool, matchers["PostToolUse"].split("|"))

    def test_41_every_command_names_an_existing_script_and_subcommand(self):
        expected = {"PreCompact": "precompact", "SessionStart": "session-start", "PreToolUse": "gate", "PostToolUse": "release"}
        for event, groups in self.config["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    self.assertEqual(hook["type"], "command")
                    self.assertIsInstance(hook["timeout"], int)
                    command = hook["command"]
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/proof_hook.py", command)
                    self.assertTrue(command.rstrip().endswith(expected[event]), command)
                    script = command.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].split('"', 1)[0]
                    self.assertTrue((PLUGIN / script).is_file(), script)
                    windows = hook["commandWindows"]
                    self.assertIn("os.environ['PLUGIN_ROOT']", windows)
                    self.assertIn("'hooks','proof_hook.py'", windows)
                    self.assertTrue(windows.rstrip().endswith(expected[event]), windows)

    @unittest.skipUnless(os.name == "nt", "commandWindows runs on Windows only")
    def test_41b_command_windows_runs_under_cmd_and_powershell(self):
        tmp = Path(tempfile.mkdtemp(prefix="proof-hook-test-"))
        self.addCleanup(shutil.rmtree, str(tmp), ignore_errors=True)
        env = dict(os.environ, PLUGIN_ROOT=str(PLUGIN), TEMP=str(tmp), TMP=str(tmp), TMPDIR=str(tmp))
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        command = self.config["hooks"]["SessionStart"][0]["hooks"][0]["commandWindows"]
        transcript = tmp / "t.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t", "name": "Skill", "input": {"skill": "proof:work"}}]}}) + "\n", encoding="utf-8")
        data = json.dumps(payload(CLAUDE, "SessionStart", source="compact",
                                  transcript_path=str(transcript))).encode("utf-8")
        for name, args, shell in (
            ("cmd", command, True),
            ("powershell", ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], False),
        ):
            with self.subTest(shell=name):
                done = subprocess.run(args, shell=shell, input=data, capture_output=True, env=env, timeout=60)
                self.assertEqual(done.returncode, 0, done.stderr)
                body = json.loads(done.stdout.decode("utf-8"))
                self.assertTrue(body["hookSpecificOutput"]["additionalContext"].startswith("proof:"))
                self.assertTrue((tmp / "proof-hooks" / (SID + ".json")).exists())
                (tmp / "proof-hooks" / (SID + ".json")).unlink()

    def test_42_the_hooks_folder_holds_only_the_known_files(self):
        self.assertEqual(sorted(p.name for p in HOOKS_DIR.iterdir() if p.name != "__pycache__"), ["hooks.json", "proof_hook.py"])

    def test_43_the_hub_path_the_hook_names_exists(self):
        self.assertTrue(HUB.is_file())

    def test_44_the_script_uses_only_the_standard_library(self):
        import ast

        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        if allowed is not None:
            self.assertLessEqual(imported, allowed)
        else:
            self.assertLessEqual(imported, {"json", "os", "sys", "tempfile", "time", "pathlib"})


if __name__ == "__main__":
    unittest.main()

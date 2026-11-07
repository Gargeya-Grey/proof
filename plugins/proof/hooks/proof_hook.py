#!/usr/bin/env python3
"""proof hooks: keep the pstack hub in use after a context summary.

One script, one subcommand per host event (Python 3.9+, standard library only):

  precompact     PreCompact      print instructions for the summary
  session-start  SessionStart    (matcher "compact") write a marker, inject context
  gate           PreToolUse      deny a file edit while the marker exists
  release        PostToolUse     delete the marker when the hub was read

The same script serves Claude Code and Codex. Both send one JSON object on stdin.
Every fault fails open: exit 0, no deny, one `proof:` line on stderr.
The only file this script writes is `<temp folder>/proof-hooks/<session_id>.json`.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HUB_SUFFIX = "references/pstack/skills/poteto-mode/SKILL.md"
HUB = PLUGIN_ROOT / HUB_SUFFIX
ROUTER = PLUGIN_ROOT / "skills" / "work" / "SKILL.md"

MARKER_DIR = "proof-hooks"
MARKER_MAX_AGE = 24 * 60 * 60  # seconds
CONTEXT_CAP = 2000  # characters of additionalContext
MESSAGE_CAP = 400  # characters of systemMessage
DENY_REASON_CAP = 1000
PRECOMPACT_CAP = 4000

EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit", "apply_patch"}
READ_TOOLS = {"read"}
SHELL_TOOLS = {
    "bash",
    "powershell",
    "exec_command",
    "shell",
    "shell_command",
    "local_shell",
    "unified_exec",
    "container.exec",
}


class Fault(Exception):
    """An expected fault; the message goes to stderr."""


def posix(path):
    return str(path).replace("\\", "/")


def warn(message):
    try:
        sys.stderr.write("proof: hook inactive (%s)\n" % message)
        sys.stderr.flush()
    except Exception:
        pass


def emit(text):
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def emit_json(obj):
    # ensure_ascii keeps the output safe on any console code page.
    emit(json.dumps(obj, ensure_ascii=True))


def clip(text, cap):
    return text if len(text) <= cap else text[:cap]


def read_payload():
    raw = sys.stdin.buffer.read()
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise Fault("input is not a JSON object")
    return data


def drain_stdin():
    try:
        sys.stdin.buffer.read()
    except Exception:
        pass


def temp_root():
    """The OS temp folder. The first of TMPDIR, TEMP, TMP that is set wins, with no fallback,
    so a bad value fails open instead of moving the marker somewhere else."""
    for name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            return Path(value)
    return Path(tempfile.gettempdir())


def marker_path(session_id):
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(session_id))[:120]
    if not safe:
        raise Fault("empty session_id")
    return temp_root() / MARKER_DIR / (safe + ".json")


def session_id_of(data):
    value = data.get("session_id")
    if not isinstance(value, str) or not value:
        raise Fault("no session_id in input")
    return value


def is_subagent(data):
    # Claude Code and Codex set agent_id when the hook fires inside a subagent.
    return bool(data.get("agent_id"))


def tool_name_of(data):
    name = data.get("tool_name")
    return name.strip().lower() if isinstance(name, str) else ""


def flatten(value, out):
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            flatten(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            flatten(item, out)


def names_hub(text):
    return HUB_SUFFIX.lower() in posix(text).lower()


def marker_is_live(path):
    """True when the marker exists, parses, and is younger than 24 hours."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            created = float(json.load(handle)["created"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    age = time.time() - created
    return 0 <= age < MARKER_MAX_AGE


def sweep(folder):
    """Delete markers older than the age limit. Never raises."""
    try:
        now = time.time()
        for entry in folder.iterdir():
            if entry.suffix == ".json" and now - entry.stat().st_mtime > MARKER_MAX_AGE:
                entry.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------- events


def do_precompact(data):
    text = (
        "proof: When you write this summary, include a section headed exactly "
        "\"Active proof files\". Under it, list one per line:\n"
        "- the absolute path of every pstack playbook, principle or skill file "
        "that this session read (files under a references/pstack/ folder; write each "
        "path in full, never shorten it);\n"
        "- the playbook step now in progress (the playbook name and the step);\n"
        "- the router path: %s\n"
        "If the session read no such file, write \"none\" under the heading. "
        "The next turn must read these files again.\n" % ROUTER
    )
    emit(clip(text, PRECOMPACT_CAP))


def session_context(hub, router):
    text = (
        "proof: the context was just summarized. Before any edit, do these in order. "
        "1) Load the `work` skill again (Claude Code: Skill `proof:work`; other hosts: the "
        "`work` skill of the proof plugin). "
        "2) Read the pstack hub in full: %s "
        "3) Read every file listed under \"Active proof files\" in the summary, or, "
        "when it has no such list, every pstack file it names (the router is %s), "
        "then continue the playbook step the summary names. "
        "4) Read the repository's AGENTS.md and CLAUDE.md. "
        "A gate denies file edits until the hub has been read." % (hub, router)
    )
    return clip(text, CONTEXT_CAP)


def do_session_start(data):
    session_id = session_id_of(data)
    source = data.get("source")
    if source not in (None, "compact"):
        return  # the matcher is "compact"; any other source does nothing
    hub, router = str(HUB), str(ROUTER)

    gate_active = False
    try:
        path = marker_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        sweep(path.parent)
        now = time.time()
        body = {
            "session_id": session_id,
            "created": now,
            "created_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "hub": hub,
        }
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        os.replace(str(tmp), str(path))
        gate_active = True
    except (OSError, Fault) as exc:
        warn("cannot write marker: %s" % exc)

    if gate_active:
        message = "proof: context summarized. The agent must re-read the pstack hub before its next edit."
    else:
        message = (
            "proof: context summarized, but the edit gate is NOT active "
            "(the temp folder is not writable). Only the reload notice was sent."
        )
    emit_json(
        {
            "systemMessage": clip(message, MESSAGE_CAP),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": session_context(hub, router),
            },
        }
    )


def do_gate(data):
    if tool_name_of(data) not in EDIT_TOOLS:
        return
    if is_subagent(data):
        return
    path = marker_path(session_id_of(data))
    if not marker_is_live(path):
        return
    reason = (
        "proof: the context was summarized and the pstack hub was not read again. "
        "Read this file in full, then repeat the edit: %s "
        "Also load the `work` skill again and read the files under \"Active proof files\" "
        "in the summary." % HUB
    )
    emit_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": clip(reason, DENY_REASON_CAP),
            }
        }
    )


def failed_shell(response):
    """True when the tool response says a shell command failed, so a failed cat does not count."""
    if not isinstance(response, dict):
        return False
    for key in ("exit_code", "exitCode", "returncode", "status_code"):
        value = response.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value != 0:
            return True
    return False


def partial_read(tool_input):
    """True when a Read call asked for only part of the hub (an offset past line 1, or a limit
    below the hub's length). The gate asks for the hub in full."""
    if not isinstance(tool_input, dict):
        return False
    offset, limit = tool_input.get("offset"), tool_input.get("limit")
    if isinstance(offset, int) and not isinstance(offset, bool) and offset > 1:
        return True
    if isinstance(limit, int) and not isinstance(limit, bool):
        try:
            with open(HUB, "rb") as handle:
                lines = handle.read().count(b"\n") + 1
        except OSError:
            return False
        return limit < lines
    return False


def do_release(data):
    name = tool_name_of(data)
    if name not in READ_TOOLS and name not in SHELL_TOOLS:
        return
    if is_subagent(data):
        return  # a subagent's read does not put the hub in the main agent's context
    path = marker_path(session_id_of(data))
    if not path.exists():
        return
    parts = []
    flatten(data.get("tool_input"), parts)
    if not any(names_hub(part) for part in parts):
        return
    if name in SHELL_TOOLS and failed_shell(data.get("tool_response")):
        return
    if name in READ_TOOLS and partial_read(data.get("tool_input")):
        return
    path.unlink()


COMMANDS = {
    "precompact": do_precompact,
    "session-start": do_session_start,
    "gate": do_gate,
    "release": do_release,
}


def main(argv):
    try:
        if len(argv) < 2 or argv[1] not in COMMANDS:
            raise Fault("unknown subcommand %r" % (argv[1] if len(argv) > 1 else ""))
        handler = COMMANDS[argv[1]]
        if argv[1] == "precompact":
            drain_stdin()  # the text does not depend on the input
            handler(None)
        else:
            handler(read_payload())
    except Fault as exc:
        warn(str(exc))
    except Exception as exc:  # fail open on every fault
        warn("%s: %s" % (type(exc).__name__, exc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

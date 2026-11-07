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

import os
import sys

FAST_COMMANDS = ("gate", "release")


def no_marker_at_all():
    """Fast path for the events that fire on every tool call. True when the marker folder holds no
    marker of any session, so the hook has nothing to do. It needs only os and sys, which Python has
    loaded before this line; the rest of the script loads only when a marker may exist. It finds the
    folder exactly as temp_root() does, and takes the full path when it is unsure."""
    if len(sys.argv) < 2 or sys.argv[1] not in FAST_COMMANDS:
        return False
    root = None
    for name in ("TMPDIR", "TEMP", "TMP"):
        if os.environ.get(name):
            root = os.environ[name]
            break
    if root is None:
        return False  # the fallback folder needs tempfile: take the full path
    try:
        names = os.listdir(os.path.join(root, "proof-hooks"))
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return not any(n.endswith(".json") for n in names)


if __name__ == "__main__" and no_marker_at_all():
    try:
        sys.stdin.buffer.read()  # read the input, so the host never writes into a closed pipe
    except Exception:
        pass
    sys.exit(0)

import json  # noqa: E402  (after the fast path on purpose)
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

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


def hub_keys():
    """The installed hub's path as a tool input may spell it: native, with forward slashes, and the
    Git Bash form of a Windows drive (W:/x -> /w/x). Lower case, so the match ignores case."""
    native = posix(os.path.normcase(str(HUB))).lower()
    keys = {native, posix(str(HUB)).lower()}
    if len(native) > 2 and native[1] == ":":
        keys.add("/" + native[0] + native[2:])
    return keys


def names_hub(text):
    """True when the text names the hub of this install. A hub of another copy (an old cache, a
    clone) does not count: the gate asks for the hub that the running plugin belongs to."""
    low = posix(text).lower()
    return any(key in low for key in hub_keys())


def is_hub_path(value):
    try:
        given = os.path.normcase(os.path.realpath(os.path.expanduser(value)))
    except (OSError, ValueError):
        return False
    return given == os.path.normcase(str(HUB))


HUB_SHARE = 0.95  # share of the hub's lines that a tool response must show


def shows_hub(texts):
    """True when the response texts show nearly every non-empty line of the hub, so the agent has
    the hub in context: a `test -f`, a `head` or a failed command shows too little."""
    try:
        with open(HUB, "r", encoding="utf-8", errors="replace") as handle:
            lines = [line.strip() for line in handle if line.strip()]
    except OSError:
        return False
    if not lines:
        return False
    blob = "\n".join(texts)
    found = sum(1 for line in lines if line in blob)
    return found >= HUB_SHARE * len(lines)


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
    name = tool_name_of(data)
    if name not in EDIT_TOOLS and name not in SHELL_TOOLS:
        return
    if is_subagent(data):
        return
    path = marker_path(session_id_of(data))
    if not marker_is_live(path):
        return
    if name in SHELL_TOOLS:
        parts = []
        flatten(data.get("tool_input"), parts)
        if any(names_hub(part) for part in parts):
            return  # a shell call that reads the hub is the way out of the gate
    reason = (
        "proof: the context was summarized and the pstack hub was not read again. "
        "File edits and shell commands wait until you read this file in full (the Read tool, "
        "or one shell command that prints the whole file): %s "
        "Then repeat the call. Also load the `work` skill again and read the files under "
        "\"Active proof files\" in the summary." % HUB
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
    tool_input = data.get("tool_input")
    response = data.get("tool_response")
    if name in READ_TOOLS:
        target = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if not isinstance(target, str) or not is_hub_path(target):
            return
    else:
        parts = []
        flatten(tool_input, parts)
        if not any(names_hub(part) for part in parts):
            return
        if failed_shell(response):
            return
    texts = []
    flatten(response, texts)
    if any(t.strip() for t in texts):
        # The response shows output: it must show the hub.
        if not shows_hub(texts):
            return
    elif name in READ_TOOLS:
        # No text in the response (a shape we have not seen): judge the Read by what it asked for.
        if partial_read(tool_input):
            return
    elif texts:
        return  # a shell call that printed nothing (`test -f`) read nothing
    # A shell response with no text fields at all is a shape we have not seen: release, so an
    # unknown host format can never hold the gate shut (fail open).
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

"""PostToolUse and PostToolUseFailure handler: append one evidence record.

Reads the hook event JSON on stdin, resolves kind, check_id and tier from
claim-ledger.toml, stats the written file on mutation events, appends one
record to the session's evidence log and exits 0 with no output. On any
failure it appends an entry to errors.log instead, writes no record, and still
exits 0: a broken recorder never interferes with the session, and the turn
handler marks a turn with an errors.log entry UNKNOWN (R-3, I-9).

Until git ignores .claude/claim-ledger/, it writes nothing at all and returns a
systemMessage instead, which Claude Code shows the user on every tool call: a
refusal nobody sees would be a silently inert ledger. Outside a repository
there is nothing to commit, so it records as usual.

- outcome comes from which event fired: ok from PostToolUse, failed from
  PostToolUseFailure, unknown from anything else. A Bash PostToolUse is also
  unknown when the command did not run to its end in the foreground: started
  in the background, backgrounded by the user or by its timeout, or
  interrupted. Its result is not known yet, so it cannot be ok (I-2).
- outcome_detail is the first line of the failure's error string, verbatim and
  never parsed, cut at log.max_command_chars. The lines after it are the
  command's output, which can hold file contents and environment values (R-7).
- command is the Bash command line cut at its first line break and at
  log.max_command_chars, which keeps heredoc bodies out of the log (R-7). The
  value of each leading NAME=value assignment is replaced by a marker, keeping
  the name. A secret passed any other way (--token=..., export, env, or after
  &&) is stored as written: a known limit. Check and tier resolution see the
  whole, unmasked command.
- turn_id is the harness's prompt id and nothing else, null when the payload
  carries none. turn_number is the session's own count of turns, read from
  sessions/<session>.turn, which the Stop handler advances; the recorder only
  reads it, since incrementing it here would be a read-modify-write across
  concurrent hooks. Both travel on every record: one word, one meaning, in the
  log and in a captured report alike.
- files, on mutation records only: the path from tool_input (file_path for
  Edit and Write, notebook_path for NotebookEdit), made project-relative with
  symlinks resolved, with its mtime from stat. A path outside the project is
  kept absolute and takes the default tier. tool_response is never copied: for
  file tools it carries file contents.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__" and not __package__:
    # Run as a script by the hook: import the ledger package from src/, and do
    # not let sibling modules in src/ledger/ shadow anything.
    sys.path[0] = str(Path(__file__).resolve().parents[1])

from ledger import config, evidence, install  # noqa: E402

#: What this component calls itself in errors.log. The turn handler reads it
#: back: a lost record is the session's problem, a failed audit is the turn's.
COMPONENT = "record"
OUTCOME_BY_EVENT = {"PostToolUse": "ok", "PostToolUseFailure": "failed"}
PATH_FIELD = {"Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}
ERRORS_LOG = evidence.STATE_DIR / "errors.log"
_LINE_BREAK = re.compile(r"[\r\n]")
_TURN_COUNTER = re.compile(r"[1-9][0-9]*\n?")
_MAX_ERROR_CHARS = 500
ASSIGNMENT_MARKER = "<redacted>"
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")


class RecordError(Exception):
    """The hook payload cannot be turned into a record."""


def main() -> int:
    """Hook entry point. Always returns 0 and never writes to stdout."""
    now = datetime.now(timezone.utc)
    raw = sys.stdin.buffer.read()
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    root = Path(project_dir or os.getcwd())
    state = install.ignore_state(root)  # one git call per tool call, no more
    if state not in (install.IGNORED, install.NO_GIT):
        refuse(root, state)
        return 0
    try:
        record_event(raw, project_dir, now)
    except Exception as error:  # every failure must reach errors.log
        report_failure(root, COMPONENT, raw, error, now)
    return 0


def record_event(raw: bytes, project_dir: str | None, now: datetime) -> dict:
    """Append the record for one hook event and return it. Raises on any failure."""
    if not project_dir:
        raise RecordError("CLAUDE_PROJECT_DIR is not set")
    root = Path(project_dir)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RecordError("hook input is not a JSON object")
    log = evidence.session_log(root, payload.get("session_id"))
    cfg = config.load(root / config.CONFIG_FILENAME)
    turn_id, turn_number = turn_ids(payload, root)
    record = build(payload, cfg, root, turn_id=turn_id, turn_number=turn_number, ts_end=now)
    evidence.append(log, record)
    # After the record, never before it: a lost record is the one failure this
    # system must not have, and seeding a hash is not worth risking one for.
    seed_config_baseline(root, payload.get("session_id"),
                         config.fingerprint(root / config.CONFIG_FILENAME))
    return record


def build(payload: dict, cfg: config.Config, root: Path, *,
          turn_id: str | None, turn_number: int, ts_end: datetime) -> dict:
    """The evidence record for one PostToolUse or PostToolUseFailure payload."""
    tool = payload.get("tool_name")
    if not isinstance(tool, str) or not tool:
        raise RecordError("hook input has no tool_name: not a tool event")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise RecordError("hook input has no tool_input object")
    session = payload.get("session_id")
    tool_use_id = payload.get("tool_use_id")
    outcome = OUTCOME_BY_EVENT.get(payload.get("hook_event_name"), "unknown")

    record: dict = {"v": evidence.RECORD_VERSION, "session": session,
                    "turn_id": turn_id, "turn_number": turn_number,
                    "tool_use_id": tool_use_id if isinstance(tool_use_id, str) else None,
                    "tool": tool}
    command = None
    relative_paths: list[str] = []
    files = None
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            raise RecordError("Bash tool_input has no command string")
        check_id = cfg.check_for(command)
        record["kind"] = "check" if check_id else "other"
        record["command"] = _cut(mask_assignments(command), cfg.log.max_command_chars)
        if check_id:
            record["check_id"] = check_id
        if outcome == "ok" and not _ran_to_end(tool_input, payload.get("tool_response")):
            outcome = "unknown"
    elif tool in PATH_FIELD:
        record["kind"] = "mutation"
        stored, target, inside = _written_path(tool_input, PATH_FIELD[tool], root)
        if inside:
            relative_paths.append(stored)
        # A failed call may not have written anything, so a missing file is
        # expected there; after a successful one it is a recorder failure.
        files = [{"path": stored, "mtime": _mtime(target, required=outcome == "ok")}]
    else:
        record["kind"] = "other"

    record["outcome"] = outcome
    error = payload.get("error")
    if outcome == "failed" and isinstance(error, str):
        record["outcome_detail"] = _cut(error, cfg.log.max_command_chars)
    record["ts_end"] = iso(ts_end)
    duration = payload.get("duration_ms")
    if (isinstance(duration, (int, float)) and not isinstance(duration, bool)
            and math.isfinite(duration) and duration >= 0):
        record["duration_ms"] = duration
    if files is not None:
        record["files"] = files
    record["tier"] = cfg.tier_for(tool, command=command, paths=relative_paths).tier
    return record


def turn_ids(payload: dict, root: Path) -> tuple[str | None, int]:
    """The harness's prompt id, which may be absent, and the session's turn number."""
    prompt_id = payload.get("prompt_id")
    turn_id = prompt_id if isinstance(prompt_id, str) and prompt_id else None
    return turn_id, read_turn_counter(turn_counter(root, payload.get("session_id")))


def turn_counter(root: Path, session: object) -> Path:
    """The per-session turn counter, beside that session's log."""
    return evidence.session_log(root, session).with_suffix(".turn")


def config_baseline(root: Path, session: object) -> Path:
    """Where this session's opening hash of claim-ledger.toml is kept (I-8)."""
    return evidence.session_log(root, session).with_suffix(".confighash")


def seed_config_baseline(root: Path, session: object, digest: str) -> None:
    """Record the config hash for this session, once. The first hook wins.

    I-8 says "when the session opens", and the earliest the ledger exists in a
    session is its first hook, so that is what opening means here. A change made
    before the ledger has run once is not detectable by anything on this side,
    and saying so is better than implying a window that does not exist.

    O_EXCL rather than a read-then-write: concurrent recorders race for this,
    and the create either wins or finds the answer already there.
    """
    path = config_baseline(root, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return
    try:
        os.write(fd, (digest + "\n").encode("ascii"))
    finally:
        os.close(fd)


def read_config_baseline(root: Path, session: object) -> str | None:
    """The hash this session opened with, or None when none was ever written."""
    try:
        return config_baseline(root, session).read_text(encoding="ascii").strip() or None
    except (FileNotFoundError, ValueError):
        return None


def read_turn_counter(counter: Path) -> int:
    """The turn number the counter holds. A missing counter means turn 1."""
    try:
        text = counter.read_text(encoding="ascii")
    except FileNotFoundError:
        return 1
    if not _TURN_COUNTER.fullmatch(text):
        raise RecordError(f"{counter.name} does not hold a turn number")
    return int(text)


def mask_assignments(command: str) -> str:
    """command with the value of each leading NAME=value replaced by the marker.

    Leading means before the first word that is not an assignment, which is
    where the shell reads assignments as the command's environment. A value
    that never closes its quote runs to the end of the command and is masked
    whole.
    """
    out, i = [], 0
    while True:
        start = i
        while start < len(command) and command[start] in " \t":
            start += 1
        name = _ASSIGNMENT.match(command, start)
        if not name:
            break
        out.append(command[i:name.end()] + ASSIGNMENT_MARKER)
        i = _word_end(command, name.end())
    return "".join(out) + command[i:]


def _word_end(text: str, i: int) -> int:
    """Index just past the shell word starting at i, quotes and $( ) included."""
    if text.startswith("(", i):  # NAME=(array values)
        return _closing_paren(text, i + 1)
    while i < len(text):
        char = text[i]
        if char in " \t\r\n;&|<>()":
            return i
        if char == "\\":
            i += 2
        elif char == "'":
            close = text.find("'", i + 1)
            i = len(text) if close == -1 else close + 1
        elif char == '"':
            i = _closing_double_quote(text, i + 1)
        elif char == "`":
            close = text.find("`", i + 1)
            i = len(text) if close == -1 else close + 1
        elif text.startswith("$(", i):
            i = _closing_paren(text, i + 2)
        else:
            i += 1
    return len(text)


def _closing_double_quote(text: str, i: int) -> int:
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text[i] == '"':
            return i + 1
        else:
            i += 1
    return len(text)


def _closing_paren(text: str, i: int) -> int:
    depth = 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 1
        elif char == "'":
            close = text.find("'", i + 1)
            if close == -1:
                return len(text)
            i = close
        elif char == '"':
            i = _closing_double_quote(text, i + 1) - 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _ran_to_end(tool_input: dict, tool_response: object) -> bool:
    """Whether a successful Bash event reports a command that finished in the foreground."""
    if tool_input.get("run_in_background") is True or not isinstance(tool_response, dict):
        return False
    if tool_response.get("interrupted") is True or tool_response.get("backgroundTaskId"):
        return False
    if tool_response.get("timedOutAfterMs") is not None:
        return False
    return not any(key.startswith("backgrounded") and value
                   for key, value in tool_response.items())


def _written_path(tool_input: dict, field: str, root: Path) -> tuple[str, Path, bool]:
    """(path as stored, resolved path, whether it is inside the project)."""
    value = tool_input.get(field)
    if not isinstance(value, str) or not value:
        raise RecordError(f"tool_input has no {field}")
    if not Path(value).is_absolute():
        raise RecordError(f"tool_input.{field} is not an absolute path")
    target = Path(os.path.realpath(value))
    try:
        return target.relative_to(os.path.realpath(root)).as_posix(), target, True
    except ValueError:
        return target.as_posix(), target, False


def mtime_of(path: Path) -> str:
    """When a file was last modified, in the one timestamp format the ledger uses.

    The join compares these against a check's ts_end as plain strings, which
    only holds because every timestamp written anywhere here has this shape.
    """
    seconds, rest = divmod(os.stat(path).st_mtime_ns, 1_000_000_000)
    moment = datetime.fromtimestamp(seconds, timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{rest // 1_000_000:03d}Z"


def _mtime(path: Path, *, required: bool) -> str | None:
    try:
        return mtime_of(path)
    except OSError:
        if required:
            raise
        return None


def iso(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _cut(text: str, limit: int) -> str:
    """text up to its first line break, and at most limit characters of it."""
    return _LINE_BREAK.split(text, maxsplit=1)[0][:limit]


def refuse(root: Path, state: str) -> None:
    """Tell the user, not the log, that nothing is being recorded."""
    message = (f"claim-ledger is not recording: git says '{install.GITIGNORE_LINE}' is "
               f"{state} in {root}, and the ledger writes nothing that git would commit. "
               f"Run: python3 {install.PLUGIN_ROOT / 'src' / 'ledger' / 'install.py'} {root}")
    sys.stdout.write(json.dumps({"systemMessage": message}) + "\n")


def report_failure(root: Path, component: str, raw: bytes, error: BaseException,
                   now: datetime) -> None:
    """Append one JSON line to errors.log. Never raises."""
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload = {}
    turn_id = payload.get("prompt_id")
    turn_number = None
    try:
        _, turn_number = turn_ids(payload, root)
    except Exception:
        pass
    entry = {"ts": iso(now), "component": component,
             "session": payload.get("session_id"),
             "turn_id": turn_id if isinstance(turn_id, str) else None,
             "turn_number": turn_number,
             "tool_use_id": payload.get("tool_use_id"),
             "error": _cut(f"{type(error).__name__}: {error}", _MAX_ERROR_CHARS)}
    line = (json.dumps(entry, ensure_ascii=True, default=str) + "\n").encode("ascii")
    try:
        path = root / ERRORS_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except OSError as failure:
        # Last resort: errors.log itself cannot be written.
        sys.stderr.write(f"claim-ledger recorder: {entry['error']} "
                         f"(errors.log not writable: {failure})\n")


if __name__ == "__main__":
    sys.exit(main())

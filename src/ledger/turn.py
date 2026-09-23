"""Stop handler, phase 0: capture the turn's report and advance the turn counter.

Nothing else runs here yet. The phase-1 pipeline — extract, join, render,
calibrate — moves in at step 8, and until then this handler reads no claim and
renders no verdict.

It writes reports/<session>-<n>.md: a header, the report text from
last_assistant_message kept verbatim, and the turn's slice of the evidence log
as the lines the log itself holds. The corpus is annotated from these files by
hand, so the text has to survive the round trip unchanged; the header carries
its length in characters, which is what lets a reader take the report back out
of a file whose text may hold anything, this file's own headings included.

- The counter in sessions/<session>.turn advances on every Stop, whether or not
  a report was captured, because a turn ended either way. The recorder only
  ever reads that file, so this is the one writer (R-5).
- corpus.capture = false writes no report and still advances the counter.
- It never exits 2. On Stop, exit 2 continues the conversation, which is the
  gate, and the gate is phase 2 (R-30). Every failure goes to errors.log
  instead, which marks the turn UNKNOWN once the pipeline reads that file.
- Like the recorder, it writes nothing at all while git does not ignore the
  state directory.
- A Stop that follows another stop hook's continuation (stop_hook_active) is
  captured as its own turn, since a turn is one agent response. The header
  carries the flag, so a reader can tell those apart from a first response.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path[0] = str(Path(__file__).resolve().parents[1])

from ledger import config, evidence, install, record  # noqa: E402

COMPONENT = "turn"
REPORTS = "reports"


class TurnError(Exception):
    """The Stop payload cannot be captured."""


def main() -> int:
    """Hook entry point. Always returns 0, and never exits 2."""
    now = datetime.now(timezone.utc)
    raw = sys.stdin.buffer.read()
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    root = Path(project_dir or os.getcwd())
    state = install.ignore_state(root)
    if state not in (install.IGNORED, install.NO_GIT):
        record.refuse(root, state)
        return 0

    try:
        if not project_dir:  # the recorder refuses too: same project or no project
            raise TurnError("CLAUDE_PROJECT_DIR is not set")
        payload = _payload(raw)
        session = payload.get("session_id")
        counter = record.turn_counter(root, session)  # also validates the session id
        number = record.read_turn_counter(counter)
    except Exception as error:  # nothing can be captured or counted without these
        record.report_failure(root, COMPONENT, raw, error, now)
        return 0

    try:
        if config.load(root / config.CONFIG_FILENAME).corpus.capture:
            unreadable = capture(root, payload, session, number, now)
            if unreadable is not None:  # the report is kept; the turn is still UNKNOWN (I-9)
                raise evidence.EvidenceError(unreadable)
    except Exception as error:
        record.report_failure(root, COMPONENT, raw, error, now)

    try:
        advance(counter, number)
    except Exception as error:
        record.report_failure(root, COMPONENT, raw, error, now)
    return 0


def capture(root: Path, payload: dict, session: str, number: int,
            now: datetime) -> str | None:
    """Write reports/<session>-<n>.md, and say why the evidence slice is empty."""
    turn_id = payload.get("prompt_id")
    turn_id = turn_id if isinstance(turn_id, str) and turn_id else None
    entries, unreadable = _slice(evidence.session_log(root, session), turn_id, number)
    report = payload.get("last_assistant_message")
    header = {
        "session": session,
        "turn_number": number,
        "turn_id": turn_id,
        "captured": record.iso(now),
        "stop_hook_active": bool(payload.get("stop_hook_active")),
        "report_chars": len(report) if isinstance(report, str) else 0,
        "records": len(entries) if unreadable is None else "unreadable",
        "positions": _positions(entries) if unreadable is None else "-",
    }
    if not isinstance(report, str):
        header["note"] = "the Stop payload carried no last_assistant_message"
        report = ""
    if unreadable is not None:
        header["note"] = f"the session log could not be read: {unreadable}"

    lines = ["---"]
    lines += [f"{key}: {value}" for key, value in header.items()]
    lines += ["---", "", "## Report", "", report, "", "## Evidence", "", "```jsonl"]
    lines += [entry.raw for entry in entries]
    lines += ["```", ""]

    path = root / evidence.STATE_DIR / REPORTS / f"{session}-{number}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    _replace(path, "\n".join(lines))
    return unreadable


def read_capture(path: Path) -> tuple[dict[str, str], str]:
    """The header of a captured report, and the report text exactly as captured.

    The text is taken by the length the header declares, so a report holding
    this file's own headings comes back whole.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise TurnError(f"{path} does not start with a captured-report header")
    header = {}
    for line in lines[1:lines.index("---", 1)]:
        key, _, value = line.partition(": ")
        header[key] = value
    marker = "\n## Report\n\n"
    if marker not in text or "report_chars" not in header:
        raise TurnError(f"{path} carries no report section")
    start = text.index(marker) + len(marker)
    return header, text[start:start + int(header["report_chars"])]


def advance(counter: Path, number: int) -> None:
    """Move the session's turn counter on by one, for the turn now starting."""
    counter.parent.mkdir(parents=True, exist_ok=True)
    _replace(counter, f"{number + 1}\n")


def _payload(raw: bytes) -> dict:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TurnError("hook input is not a JSON object")
    event = payload.get("hook_event_name")
    if event != "Stop":
        raise TurnError(f"not a Stop event: {event!r}")
    return payload


def _slice(log: Path, turn_id: str | None,
           number: int) -> tuple[list[evidence.Entry], str | None]:
    """The turn's records in file order, or an empty slice and why it is empty.

    The prompt id picks the turn out when the harness gave one, since a missed
    Stop would leave two turns sharing a number; the count is what is left.
    """
    def mine(record):
        if turn_id is not None:
            return record.get("turn_id") == turn_id
        return record.get("turn_id") is None and record.get("turn_number") == number

    try:
        return [e for e in evidence.read(log) if mine(e.record)], None
    except evidence.EvidenceError as e:
        return [], str(e)


def _positions(entries: list[evidence.Entry]) -> str:
    """Each position on its own: a turn's records need not be contiguous."""
    return ",".join(str(entry.position) for entry in entries) if entries else "-"


def _replace(path: Path, text: str) -> None:
    """Write the whole file through a rename, so a reader never sees half of it."""
    staged = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)


if __name__ == "__main__":
    sys.exit(main())

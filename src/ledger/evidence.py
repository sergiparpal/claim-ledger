"""The session evidence log: the writer and the reader, nothing else.

One JSONL file per session under .claude/claim-ledger/sessions/. A record is
appended with a single write() on an O_APPEND descriptor, so recorders running
concurrently for parallel tool calls neither interleave nor need a lock.

A record's position in the file is its order, and the only ordering that
survives: the harness stamps a hook when the call returns, so ts_end cannot
order a check against an edit that overlapped it (R-3). The reader therefore
hands each record back inside an Entry carrying that position, so that a caller
orders records by what the file says rather than by a timestamp or by the
order it happens to iterate. Nothing here reads a record back in order to
write the next one.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

STATE_DIR = Path(".claude") / "claim-ledger"
RECORD_VERSION = 2  # 2: turn split into turn_id and turn_number
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]+")  # also keeps the path inside sessions/


class EvidenceError(Exception):
    """The session log cannot be written or read as specified."""


@dataclass(frozen=True)
class Entry:
    """One record, with the file position that orders it."""

    position: int  # 1-based line number: the record's order in the session (R-3)
    record: Mapping[str, object]
    raw: str  # the line as written, for a corpus slice that is the log verbatim


def session_log(root: Path, session: object) -> Path:
    """The evidence log of one session, under the project root."""
    if not isinstance(session, str) or not _SESSION_ID.fullmatch(session):
        raise EvidenceError(f"unusable session id {session!r}")
    return root / STATE_DIR / "sessions" / f"{session}.jsonl"


def append(log: Path, record: dict) -> None:
    """Append one record as one line, in a single write() call."""
    data = (json.dumps(record, ensure_ascii=True) + "\n").encode("ascii")
    log.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(fd, data)
    finally:
        os.close(fd)
    if written != len(data):
        raise EvidenceError(f"short write to {log}: {written} of {len(data)} bytes")


def read(log: Path) -> list[Entry]:
    """Every record of a session log as an Entry, in file order.

    No log means no records. A line that is not a complete version-1 record
    raises EvidenceError: the reader never skips or repairs evidence, since a
    skipped line would shift every position after it.
    """
    try:
        raw = log.read_bytes()
    except FileNotFoundError:
        return []
    lines = raw.split(b"\n")
    if lines[-1]:
        raise EvidenceError(f"{log}:{len(lines)}: last record has no line end")
    entries = []
    for position, line in enumerate(lines[:-1], 1):
        try:
            record = json.loads(line)
        except ValueError as e:
            raise EvidenceError(f"{log}:{position}: not a JSON record") from e
        if not isinstance(record, dict) or record.get("v") != RECORD_VERSION:
            raise EvidenceError(f"{log}:{position}: not a version {RECORD_VERSION} record")
        entries.append(Entry(position, record, line.decode("utf-8")))
    return entries

"""Print a claim-ledger session log as a table. A dumper, not a checker.

    python3 tools/dump_session.py [--root PROJECT] [SESSION_ID | LOG_PATH]

With no session, lists the session logs under PROJECT/.claude/claim-ledger/
sessions/. With one, prints every record in file order under the position the
reader gives it, which is the log's only ordering. Nothing is compared, filtered, summarised or judged: the table
shows what the log holds and nothing about whether it should hold it. Turn ids
are cut to their first 8 characters; everything else is printed in full, so a
cell longer than its column shifts the rest of its row. PROJECT defaults to the
current directory.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ledger import evidence  # noqa: E402

COLUMNS = ["#", "ts_end", "turn", "turn_id", "tool", "kind", "outcome", "tier", "check_id",
           "duration_ms", "command / files", "outcome_detail"]
_MAX_PADDED = 60  # wider cells are printed whole, not padded or cut


def row(entry: evidence.Entry) -> list[str]:
    position, record = entry.position, entry.record
    turn_id = record.get("turn_id")
    target = record.get("command")
    if "files" in record:
        target = ", ".join(f"{f.get('path')} (mtime {f.get('mtime')})" for f in record["files"])
    cells = [position, record.get("ts_end"), record.get("turn_number"),
             turn_id[:8] if isinstance(turn_id, str) else turn_id, record.get("tool"), record.get("kind"), record.get("outcome"), record.get("tier"),
             record.get("check_id"), record.get("duration_ms"), target,
             record.get("outcome_detail")]
    return ["-" if cell is None else str(cell) for cell in cells]


def render(entries: list[evidence.Entry]) -> str:
    table = [COLUMNS] + [row(entry) for entry in entries]
    widths = [min(max(len(r[i]) for r in table), _MAX_PADDED) for i in range(len(COLUMNS) - 1)]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(r, widths)) + "  " + r[-1]
             for r in table]
    return "\n".join(line.rstrip() for line in lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Print a claim-ledger session log as a table.")
    parser.add_argument("--root", type=Path, default=Path("."), help="project root (default: .)")
    parser.add_argument("session", nargs="?", help="session id, or the path of a session log")
    args = parser.parse_args(argv[1:])
    sessions = args.root / evidence.STATE_DIR / "sessions"

    if args.session is None:
        logs = sorted(sessions.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not logs:
            print(f"no session logs under {sessions}")
        for log in logs:
            written = datetime.fromtimestamp(log.stat().st_mtime).isoformat(" ", "seconds")
            lines = log.read_bytes().count(b"\n")
            print(f"{log.stem}  {lines} lines  last written {written}")
        return 0

    log = Path(args.session)
    if not log.is_file():
        try:
            log = evidence.session_log(args.root, args.session)
        except evidence.EvidenceError as e:
            print(e, file=sys.stderr)
            return 1
    if not log.is_file():
        print(f"no session log at {log}", file=sys.stderr)
        return 1
    try:
        entries = evidence.read(log)
    except evidence.EvidenceError as e:
        print(f"cannot read {log}: {e}", file=sys.stderr)
        return 1
    print(f"{log}  ({len(entries)} records, in file order)")
    print(render(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

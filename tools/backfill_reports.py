#!/usr/bin/env python3
"""Rebuild captured reports from Claude Code transcripts, for a project the plugin never ran in.

    python3 tools/backfill_reports.py [--dry-run] TRANSCRIPTS_DIR ROOT

TRANSCRIPTS_DIR is a project's folder under ~/.claude/projects/, one JSONL
transcript per session. Each assistant message of a session's main thread that
ended its turn, stop_reason end_turn, is what the Stop handler would have been
given as last_assistant_message; a turn interrupted or cut by an API error does
not end so, and the handler captures none either. The message's text blocks,
in order, are the report. It is written as the handler writes one, through
ledger.turn.capture, to ROOT/.claude/claim-ledger/reports/<session>-<n>.md,
with n counting those messages in the session in the order they were sent, and
with a header note saying that it was rebuilt and that no evidence was
recorded, since the plugin was not there to record any. A message found in
several transcripts, as a resumed session copies its history, is written once.

Nothing is read but the transcripts, and nothing is written under the project
they came from: ROOT is a folder of its own, which tools/annotate_model.py and
tools/measure_route.py take as a project. A report already written is left as
it is, so a second run adds only what the first did not see. --dry-run counts
and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ledger import evidence, turn  # noqa: E402

NOTE = ("rebuilt from the session transcript by tools/backfill_reports.py; the plugin was "
        "not installed, so no evidence was recorded")


@dataclass(frozen=True)
class Rebuilt:
    session: str
    sent: str               # the ISO time of the message's last entry, when the turn ended
    text: str
    prompt_id: str | None   # the prompt that opened the turn, when the transcript names it


def turn_ends(paths: Iterable[Path]) -> list[Rebuilt]:
    """Every message that ended a turn on a main thread, once, in the order sent."""
    entries: dict[str, list[dict]] = {}     # message id -> its entries, from one transcript
    prompts: dict[str, str | None] = {}
    for path in sorted(paths):
        seen_here: dict[str, list[dict]] = {}
        prompt = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("isSidechain"):
                continue
            message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            if entry.get("type") == "user" and entry.get("promptId"):
                prompt = entry["promptId"]
            if entry.get("type") != "assistant" or not message.get("id"):
                continue
            seen_here.setdefault(message["id"], []).append(entry)
            prompts.setdefault(message["id"], prompt)
        for message_id, found in seen_here.items():
            entries.setdefault(message_id, found)    # the first transcript to hold it
    rebuilt = []
    for message_id, found in entries.items():
        if not any((e["message"].get("stop_reason") == "end_turn") for e in found):
            continue
        text = "\n\n".join(block["text"] for e in found
                           for block in e["message"].get("content") or []
                           if isinstance(block, dict) and block.get("type") == "text"
                           and block.get("text"))
        if not text.strip():
            continue
        rebuilt.append(Rebuilt(session=found[0]["sessionId"], sent=found[-1]["timestamp"],
                               text=text, prompt_id=prompts.get(message_id)))
    return sorted(rebuilt, key=lambda r: (r.session, r.sent))


def write(rebuilt: Sequence[Rebuilt], root: Path) -> tuple[int, int]:
    """Write each report the handler's way; returns how many were new and how many kept."""
    new = kept = 0
    number: dict[str, int] = {}
    for report in rebuilt:
        number[report.session] = number.get(report.session, 0) + 1
        path = root / evidence.STATE_DIR / turn.REPORTS / f"{report.session}-{number[report.session]}.md"
        if path.exists():
            kept += 1
            continue
        payload = {"last_assistant_message": report.text}
        if report.prompt_id:
            payload["prompt_id"] = report.prompt_id
        when = datetime.fromisoformat(report.sent.replace("Z", "+00:00"))
        turn.capture(root, payload, report.session, number[report.session], when, [], None)
        text = path.read_text(encoding="utf-8")
        head, _, rest = text.partition("\n---\n")
        path.write_text(f"{head}\nnote: {NOTE}\n---\n{rest}", encoding="utf-8")
        new += 1
    return new, kept


def main(argv: Sequence[str], *, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="backfill_reports.py", description=__doc__.split("\n")[0])
    parser.add_argument("transcripts", type=Path, help="a project's folder under ~/.claude/projects/")
    parser.add_argument("root", type=Path, help="the folder the reports are written under")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv)[1:])
    rebuilt = turn_ends(args.transcripts.glob("*.jsonl"))
    sessions = len({report.session for report in rebuilt})
    print(f"{len(rebuilt)} turns ended with a message holding text, in {sessions} sessions",
          file=out)
    if args.dry_run:
        return 0
    new, kept = write(rebuilt, args.root)
    print(f"written {new}, already there {kept}, under "
          f"{args.root / evidence.STATE_DIR / turn.REPORTS}", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

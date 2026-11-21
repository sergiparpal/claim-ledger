"""claim-ledger-band's reader: this turn's appendix, and the band's one line.

The mod runs it at turn.complete, after the Stop hooks have run, as

    python3 -I band.py <transcript> [<reason>]

and draws what it prints: one JSON object, {"band", "level", "appendix"}.
`reason` is turn.complete's, `answer` when left out.

The appendix is claim-ledger's Stop hook `systemMessage` as the transcript
keeps it, read back and passed on whole. It is shown to the person, never to
the model: nothing a mod draws enters the model's context, and this script
answers only the mod.

The band is one line made from it, and I-5 decides how. The one-line forms,
collapsed and UNKNOWN, are shown as they are. An expanded appendix is shown as
the groups it lists, in the order the renderer wrote them, which is severity
first (R-29), each with how many entries it holds, then the appendix's own
last line. A line that left a group out, or put a milder one first, would read
milder than the worst claim, which I-5 forbids.

A turn whose appendix is not there says so, and an answered one says it as an
error: the turn went unaudited, and showing an earlier turn's appendix in its
place would read as a clean turn (I-9).

Standard library only, and nothing from the ledger package: the mod runs this
from its own folder. tests/test_band.py holds it to what ledger.appendix
renders, so a change to the renderer that this would misread fails the suite.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator

HEAD = "claim-ledger"

#: The groups an expanded appendix can list, in the order ledger.appendix
#: writes them: its LISTED verdicts, then the two that are not verdicts.
GROUPS = ("CONTRADICTED", "UNKNOWN", "STALE", "UNSUPPORTED", "UNREPORTED",
          "EXTRACTION DEFECTS")

#: The groups that make the band an error, and the one that makes it a
#: warning. Any other group leaves it a note: UNSUPPORTED stands in most
#: turns' appendices (301 of distiller's 584 to 20 November 2026), and a band
#: that warned on every turn would be read as the folded notice was.
SEVERE = ("CONTRADICTED", "UNKNOWN")
WARNING = ("STALE",)

#: An entry's first line in each group. A scope or an action over several
#: lines continues unindented, so only its first line can match.
ENTRY = {
    "UNREPORTED": re.compile(r" \([A-Z]+\)$"),          # the action, then its tier
    "EXTRACTION DEFECTS": re.compile(r'^  ".*" — '),    # the span, then the reason
}
CLAIM = re.compile(r'^  ".*"$')                         # the span, alone on its line

#: The appendix's last line, the counts it always ends with.
TRAILER = re.compile(r"^\d+ verified, \d+ unchecked · \d+ checks? seen( · .+)?$")

#: What the band says when the turn has no appendix, by turn.complete's reason.
MISSING = {
    "answer": (f"{HEAD} · no appendix for this turn", "error"),
    "aborted": (f"{HEAD} · not audited: the turn was interrupted", "warn"),
    "error": (f"{HEAD} · not audited: the turn ended on an API error", "warn"),
    "refusal": (f"{HEAD} · not audited: the model refused", "warn"),
}
NO_TRANSCRIPT = (f"{HEAD} · no transcript to read", "error")
UNREADABLE = (f"{HEAD} · this appendix could not be summarised: open it", "error")

BLOCK = 1 << 16


def lines_from_end(path: str, block: int = BLOCK) -> Iterator[bytes]:
    """The file's lines, last first, read from its end a block at a time.

    Split on "\\n" alone: a row's JSON may hold any other line separator inside
    a string, and splitting there would cut the row in two."""
    with open(path, "rb") as file:
        end = file.seek(0, os.SEEK_END)
        tail = b""
        while end > 0:
            start = max(0, end - block)
            file.seek(start)
            parts = (file.read(end - start) + tail).split(b"\n")
            end = start
            tail = parts[0]
            yield from reversed(parts[1:])
        yield tail


def this_turns_appendix(path: str) -> str | None:
    """The appendix the Stop hook left after the turn's last answer, or None.

    Read back from the end of the transcript. The appendix row stands after
    the turn's final assistant message, so reaching an assistant row, or a row
    with a `promptId` (the turn's own user rows), before finding one means the
    turn's last Stop left none, and an earlier turn's is never taken for it."""
    for line in lines_from_end(path):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue                    # a row still being written
        if not isinstance(row, dict):
            continue
        if row.get("type") == "assistant" or "promptId" in row:
            return None
        text = _appendix_of(row)
        if text is not None:
            return text
    return None


def _appendix_of(row: dict) -> str | None:
    if row.get("type") != "attachment":
        return None
    attachment = row.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != "hook_system_message":
        return None
    if attachment.get("hookEvent", "Stop") != "Stop":
        return None
    text = attachment.get("content")
    if not isinstance(text, str):
        return None
    if text == HEAD or text.startswith(f"{HEAD} · ") or text.startswith(f"{HEAD}\n"):
        return text
    return None


def band(appendix: str | None, reason: str = "answer") -> tuple[str, str]:
    """The band's line and its level: `error`, `warn`, `note` or `quiet`.

    The level only colours the line. What it says is the appendix's, so a
    milder colour never makes the line read milder than its worst group."""
    if appendix is None:
        return MISSING.get(reason, MISSING["answer"])
    if "\n" not in appendix:
        if appendix.startswith(f"{HEAD} · UNKNOWN · "):
            return appendix, "error"
        if appendix.startswith(f"{HEAD} · ") and appendix.endswith(" · nothing unreported"):
            return appendix, "quiet"
        return UNREADABLE
    lines = appendix.split("\n")
    if lines[0] != HEAD:
        return UNREADABLE
    groups: list[list] = []                      # [name, entries], in the appendix's order
    for before, line in zip(lines, lines[1:]):
        if line in GROUPS and before == "":
            groups.append([line, 0])
        elif groups and ENTRY.get(groups[-1][0], CLAIM).search(line):
            groups[-1][1] += 1
    trailer = lines[-1] if TRAILER.match(lines[-1]) else None
    if not groups and trailer is None:
        return UNREADABLE
    parts = [HEAD, *(f"{name} {entries}" for name, entries in groups)]
    parts.append(trailer if trailer is not None else "appendix cut short")
    named = {name for name, _ in groups}
    if trailer is None or named & set(SEVERE):
        level = "error"
    elif named & set(WARNING):
        level = "warn"
    elif named:
        level = "note"
    else:
        level = "quiet"
    return " · ".join(parts), level


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not 1 <= len(args) <= 2:
        print("usage: band.py <transcript> [<reason>]", file=sys.stderr)
        return 2
    path, reason = args[0], args[1] if len(args) == 2 else "answer"
    try:
        text = this_turns_appendix(path)
    except FileNotFoundError:
        text, (line, level) = None, NO_TRANSCRIPT
    else:
        line, level = band(text, reason)
    json.dump({"band": line, "level": level, "appendix": text}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The ledger appendix: one line unless something needs saying.

A ledger nobody reads is the failure this design is most likely to die of, so
the collapsed form is the normal one and every expansion has to earn itself.
It expands when a claim is anything but VERIFIED or NOT_CHECKABLE, when a
consequential action went unmentioned, when the model pointed at a sentence
the report does not have, or when the turn is UNKNOWN.

Severity order is the one rule here that is shared with the rest of the system
(I-5). It decides which group leads, and it decides what survives the 10,000
character cap the harness puts on a systemMessage: entries go from the least
severe upward, and the line that says how many were dropped is itself never
dropped. CONTRADICTED stands at the head and alone (R-29).

What a verdict is joined to travels with it, as join wrote it, and is never
reformatted here (I-4). A scope says "failed", not "exited 1": the exit code is
deliberately not in the log, because the harness's error string is not a stable
format and parsing it is how a CONTRADICTED goes wrong.

NOT_CHECKABLE claims are counted and never listed. Listing opinions back to
their author is noise, and it is the one thing that would make the appendix
read as a critic rather than a record. VERIFIED is counted for the same reason.
The appendix reaches the user through systemMessage and never enters the
model's context: feeding it back teaches the agent which claims get caught,
which is Goodhart by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ledger import config, coverage, join, schema

#: Most severe first (I-5). The whole order, in one place: it leads the
#: appendix, and it is what the cap drops from the far end of.
SEVERITY = (join.CONTRADICTED, join.UNKNOWN, join.STALE, join.UNSUPPORTED,
            join.NOT_CHECKABLE, join.VERIFIED)

#: Listed one by one, in this order. The rest are counted in the last line.
LISTED = (join.CONTRADICTED, join.UNKNOWN, join.STALE, join.UNSUPPORTED)

#: An UNSUPPORTED claim has no record to point at, so it says what was looked for.
NOTHING_FOUND = {
    "suite_passed": "no run of that check in this session",
    "command_run": "no matching command in this session",
    "file_changed": "no record of that file being written in this session",
}

HEAD = "claim-ledger"
LIMIT = 10_000       # the harness's cap on a systemMessage
SPAN_LIMIT = 120     # a span longer than this is elided in its middle
ELLIPSIS = " … "


@dataclass(frozen=True)
class Turn:
    """Everything the appendix has to say about one turn."""

    judged: Sequence[join.Judged] = ()
    unreported: Sequence[coverage.Unreported] = ()
    checks_seen: int = 0
    defects: Sequence[schema.Defect] = ()
    unknown: str | None = None      # the turn itself failed: the reason, in one line
    dropped: int = field(default=0, compare=False)


def render(turn: Turn) -> str:
    """The appendix, ready for systemMessage, inside the harness's cap."""
    text = _render(turn)
    if len(text) <= LIMIT:
        return text
    # Drop from the least severe upward until it fits, and say how many went.
    listed = [j for j in turn.judged if j.verdict in LISTED]
    order = sorted(range(len(listed)), key=lambda i: SEVERITY.index(listed[i].verdict))
    for dropped in range(1, len(listed) + 1):
        keep = {id(listed[i]) for i in order[:len(listed) - dropped]}
        trimmed = Turn(judged=[j for j in turn.judged
                               if j.verdict not in LISTED or id(j) in keep],
                       unreported=turn.unreported, checks_seen=turn.checks_seen,
                       defects=turn.defects, unknown=turn.unknown, dropped=dropped)
        text = _render(trimmed)
        if len(text) <= LIMIT:
            return text
    return text[:LIMIT]


def _render(turn: Turn) -> str:
    if turn.unknown is not None:
        return f"{HEAD} · UNKNOWN · {turn.unknown} · {_checks(turn.checks_seen)}"
    if _collapses(turn):
        return (f"{HEAD} · {_counts(turn)} · {_checks(turn.checks_seen)} · "
                f"nothing unreported")

    lines = [HEAD]
    for verdict in LISTED:
        entries = [j for j in turn.judged if j.verdict == verdict]
        if entries:
            lines += ["", verdict]
            for judged in entries:
                lines.append(f'  "{elide(judged.claim.span)}"')
                lines.append(f"  {judged.scope or NOTHING_FOUND.get(judged.claim.type, '')}")
    listed = [u for u in turn.unreported if u.tier != config.LOW]
    if listed:
        lines += ["", "UNREPORTED"]
        lines += [f"  {u.what} ({u.tier})" for u in listed]
    if turn.defects:
        lines += ["", "EXTRACTION DEFECTS"]
        lines += [f'  "{elide(d.span)}" — {d.reason}' for d in turn.defects]

    trailer = [_counts(turn), _checks(turn.checks_seen)]
    low = len(turn.unreported) - len(listed)
    if low:
        trailer.append(f"{low} LOW-tier action{'s' if low != 1 else ''} not listed")
    if turn.dropped:
        trailer.append(f"{turn.dropped} entr{'ies' if turn.dropped != 1 else 'y'} "
                       f"dropped to fit")
    lines += ["", " · ".join(trailer)]
    return "\n".join(lines)


def _collapses(turn: Turn) -> bool:
    """R-29: one line when there is nothing to report, and only then."""
    return (not turn.defects
            and not turn.unreported
            and all(j.verdict in (join.VERIFIED, join.NOT_CHECKABLE) for j in turn.judged))


def _counts(turn: Turn) -> str:
    verified = sum(1 for j in turn.judged if j.verdict == join.VERIFIED)
    unchecked = sum(1 for j in turn.judged if j.verdict == join.NOT_CHECKABLE)
    return f"{verified} verified, {unchecked} unchecked"


def _checks(seen: int) -> str:
    """R-29 asks for this even when it is zero, which is when it says most."""
    return f"{seen} check{'s' if seen != 1 else ''} seen"


def elide(span: str) -> str:
    """A long span, shortened in the middle. The calibration log keeps it whole."""
    span = span.replace("\n", " ")
    if len(span) <= SPAN_LIMIT:
        return span
    keep = SPAN_LIMIT - len(ELLIPSIS)
    head = (keep + 1) // 2
    return span[:head] + ELLIPSIS + span[len(span) - (keep - head):]

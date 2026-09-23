"""The consequential actions a report never mentions.

R-22 settles what counts: a file mutation, a check that failed, or a command
at a tier above the default. Whether an action is consequential comes from the
consequence table, never from a guess about the command (R-23).

What a claim "names" is decided by the same matchers the join uses, so a claim
that would verify against a record also excuses that record from this list. A
report saying only "done" excuses nothing, which is the point (I-7).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ledger import config, evidence, join, schema

#: Only their order matters: a tier above the default is consequential.
TIER_RANK = {config.LOW: 0, config.REVIEW: 1, config.HUMAN: 2}


@dataclass(frozen=True)
class Unreported:
    """One consequential action, and where in the log it sits."""

    position: int
    kind: str
    what: str      # the file written, or the command run
    tier: str
    record: Mapping


def unreported(entries: Sequence[evidence.Entry], claims: Iterable[schema.Claim], *,
               default_tier: str = config.REVIEW) -> tuple[Unreported, ...]:
    """Every consequential action of these entries that no claim names."""
    named = [c for c in claims if c.type in ("file_changed", "command_run")]
    listed = []
    for entry in entries:
        written = entry.record
        if not _consequential(written, default_tier) or _named_by(named, written):
            continue
        listed.append(Unreported(position=entry.position, kind=written.get("kind", "other"),
                                 what=_what(written), tier=written.get("tier", default_tier),
                                 record=written))
    return tuple(listed)


def _consequential(written: Mapping, default_tier: str) -> bool:
    kind = written.get("kind")
    if kind == "mutation":
        # A write that failed changed nothing; one whose outcome is unknown may have.
        return written.get("outcome") != "failed"
    if kind == "check" and written.get("outcome") == "failed":
        return True
    return TIER_RANK.get(written.get("tier"), 1) > TIER_RANK.get(default_tier, 1)


def _named_by(claims: Sequence[schema.Claim], written: Mapping) -> bool:
    return any(join.names_path(c.referents, written) or join.names_command(c.referents, written)
               for c in claims)


def _what(written: Mapping) -> str:
    if written.get("kind") == "mutation":
        return ", ".join(f.get("path", "?") for f in written.get("files") or []) or "?"
    return written.get("command") or written.get("tool", "?")

"""Referent matching and the verdict table.

No model runs here. Given a claim and the log, the verdict is a lookup, and
the lookup is the one table below: data, not branching. What the code around
it does is decide which record the claim is about and what state that record
is in, and both of those refuse to guess.

Two rules keep the join from manufacturing a verification:

- A referent that names something and resolves to nothing is UNSUPPORTED. It
  never falls back to the session's only check, because "the migration script"
  resolving to the test suite would verify a claim nobody made.
- Freshness is both tests of R-18. A check is stale when a mutation of a file
  it covers sits later in the log, or when a covered file's mtime on disk is
  later than the check's own end. The first catches what the agent did, the
  second what happened outside it, and neither can remove staleness the other
  found. The timestamps compare as strings because every one of them is
  written in the same UTC format, to the millisecond.

The second test reads the working tree, so it reads what a person would call
the project: not .git, not the ledger's own writing, and nothing git ignores.
A scope of `**/*` would otherwise be staled by a `git add`, or by a build
directory, neither of which is a change to a file the check covers.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ledger import config, evidence, record, schema

VERIFIED = "VERIFIED"
CONTRADICTED = "CONTRADICTED"
STALE = "STALE"
UNSUPPORTED = "UNSUPPORTED"
NOT_CHECKABLE = "NOT_CHECKABLE"
UNKNOWN = "UNKNOWN"

#: What the log says about the evidence a claim points at.
NONE, OK, OUTDATED, FAILED, UNCLEAR = "none", "ok", "outdated", "failed", "unclear"

#: The whole mapping from claim type and evidence state to verdict (R-21).
VERDICT_TABLE: Mapping[tuple[str, str], str] = {
    ("suite_passed", NONE): UNSUPPORTED,
    ("suite_passed", OK): VERIFIED,
    ("suite_passed", OUTDATED): STALE,
    ("suite_passed", FAILED): CONTRADICTED,
    ("suite_passed", UNCLEAR): UNKNOWN,
    ("command_run", NONE): UNSUPPORTED,
    ("command_run", OK): VERIFIED,      # it ran; the outcome travels in the scope
    ("command_run", FAILED): VERIFIED,
    ("command_run", UNCLEAR): UNKNOWN,
    ("file_changed", NONE): UNSUPPORTED,
    ("file_changed", OK): VERIFIED,
    ("file_changed", FAILED): UNSUPPORTED,   # a write that failed changed nothing
    ("file_changed", UNCLEAR): UNSUPPORTED,
    ("judgment", NONE): NOT_CHECKABLE,
    ("intent", NONE): NOT_CHECKABLE,
}


@dataclass(frozen=True)
class Judged:
    """One claim, its verdict, and the evidence that decided it."""

    claim: schema.Claim
    verdict: str
    scope: str | None      # I-4: never a bare verdict
    position: int | None   # where in the log the deciding record sits


def judge(claims: Iterable[schema.Claim], entries: Sequence[evidence.Entry], *,
          cfg: config.Config, root: Path) -> tuple[Judged, ...]:
    """A verdict for every claim, in the order they were made."""
    return tuple(_judge(claim, entries, cfg, root) for claim in claims)


def _judge(claim: schema.Claim, entries: Sequence[evidence.Entry],
           cfg: config.Config, root: Path) -> Judged:
    if claim.type in ("judgment", "intent"):
        return Judged(claim, VERDICT_TABLE[(claim.type, NONE)], None, None)
    if claim.type == "suite_passed":
        entry, state, note = _suite(claim, entries, cfg, root)
    elif claim.type == "command_run":
        entry, state, note = _command(claim, entries)
    else:
        entry, state, note = _file(claim, entries)
    verdict = VERDICT_TABLE[(claim.type, state)]
    scope = _scope(entry.record, note) if entry is not None else None
    return Judged(claim, verdict, scope, entry.position if entry is not None else None)


def check_ids_for(referents: Sequence[str], cfg: config.Config) -> tuple[set[str], bool]:
    """The checks a claim's referents name, and whether they named anything at all."""
    resolved = set()
    for referent in referents:
        word = referent.strip()
        for candidate in (cfg.invocations.get(word), cfg.aliases.get(word.lower())):
            if candidate:
                resolved.add(candidate)
        if any(check.check_id == word for check in cfg.checks):
            resolved.add(word)
    return resolved, bool(referents)


def _suite(claim, entries, cfg, root):
    wanted, named = check_ids_for(claim.referents, cfg)
    if named and not wanted:
        return None, NONE, None          # it named a suite we do not know: never a fallback
    if not named:
        seen = {e.record.get("check_id") for e in entries if e.record.get("kind") == "check"}
        seen.discard(None)
        if len(seen) != 1:
            return None, NONE, None
        wanted = seen
    found = [e for e in entries
             if e.record.get("kind") == "check" and e.record.get("check_id") in wanted]
    if not found:
        return None, NONE, None
    entry = found[-1]                    # the last run is the one a claim is about
    outcome = entry.record.get("outcome")
    if outcome != "ok":
        return entry, FAILED if outcome == "failed" else UNCLEAR, None
    stale_because = _stale_because(entry, entries, cfg, root)
    return entry, (OUTDATED if stale_because else OK), stale_because


def _command(claim, entries):
    found = [e for e in entries if names_command(claim.referents, e.record)]
    if not found:
        return None, NONE, None
    entry = found[-1]
    outcome = entry.record.get("outcome")
    return entry, {"ok": OK, "failed": FAILED}.get(outcome, UNCLEAR), None


def _file(claim, entries):
    found = [e for e in entries if names_path(claim.referents, e.record)]
    if not found:
        return None, NONE, None
    entry = found[-1]
    outcome = entry.record.get("outcome")
    return entry, {"ok": OK, "failed": FAILED}.get(outcome, UNCLEAR), None


def names_command(referents: Sequence[str], written: Mapping) -> bool:
    """First token equal, and every further token the claim names present."""
    command = written.get("command")
    if not isinstance(command, str):
        return False
    tokens = command.split()
    for referent in referents:
        named = referent.split()
        if named and tokens and named[0] == tokens[0] and set(named[1:]) <= set(tokens[1:]):
            return True
    return False


def names_path(referents: Sequence[str], written: Mapping) -> bool:
    if written.get("kind") != "mutation":
        return False
    paths = {f.get("path") for f in written.get("files") or []}
    return any(referent.strip() in paths for referent in referents)


def _stale_because(check: evidence.Entry, entries: Sequence[evidence.Entry],
                   cfg: config.Config, root: Path) -> str | None:
    """Why the check is out of date, by either test of R-18, or None."""
    globs = cfg.scopes.get(check.record.get("check_id"), ())
    for entry in entries:
        if entry.position <= check.position or entry.record.get("kind") != "mutation":
            continue
        for written in entry.record.get("files") or []:
            path = written.get("path")
            if isinstance(path, str) and _covered(path, globs):
                return f"{path} was written after it, at log position {entry.position}"
    newest = _newest(root, globs)
    ran_at = check.record.get("ts_end") or ""
    if newest and newest[1] > ran_at:
        return f"{newest[0]} was modified at {newest[1]}, after it ran at {ran_at}"
    return None


def _covered(path: str, globs: Sequence[config.Glob]) -> bool:
    return any(glob.matches(path) for glob in globs)


def _newest(root: Path, globs: Sequence[config.Glob]) -> tuple[str, str] | None:
    """The most recently modified file a check covers, and when, read from disk."""
    covered = []
    for folder, folders, files in os.walk(root):
        here = Path(folder)
        folders[:] = [f for f in folders if f != ".git"           # git's own bookkeeping
                      and here / f != root / evidence.STATE_DIR]  # and our own writing
        covered += [path for path in ((here / name).relative_to(root).as_posix()
                                      for name in files) if _covered(path, globs)]
    newest = None
    for relative in _not_ignored(root, covered):
        try:
            stamped = record.mtime_of(root / relative)
        except OSError:
            continue              # it went away while we looked; the log still holds its record
        if newest is None or stamped > newest[1]:
            newest = (relative, stamped)
    return newest


def _not_ignored(root: Path, paths: Sequence[str]) -> Sequence[str]:
    """The paths git would keep. A file git ignores is not the project's work.

    One call for the whole list, since asking per file would cost more than the
    walk itself. Where there is no git, or no repository, nothing is ignored.
    """
    if not paths:
        return paths
    try:
        # -z makes the input NUL-separated as well as the output, which is why
        # the paths are joined that way and not by newline.
        asked = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=root,
                               input="\0".join(paths).encode(), capture_output=True,
                               timeout=10)
    except (OSError, subprocess.SubprocessError):
        return paths
    if asked.returncode not in (0, 1):   # 128: not a repository, or git could not say
        return paths
    ignored = {name for name in asked.stdout.decode("utf-8", "replace").split("\0") if name}
    return [path for path in paths if path not in ignored]


def _scope(written: Mapping, note: str | None) -> str:
    """What travels with a verdict, so that none of them is bare (I-4)."""
    if written.get("kind") == "mutation":
        paths = ", ".join(f.get("path", "?") for f in written.get("files") or [])
        scope = f"{paths} written {written.get('outcome')} at {written.get('ts_end')}"
    else:
        scope = (f"{written.get('command')} {written.get('outcome')} "
                 f"at {written.get('ts_end')}")
    return f"{scope}; {note}" if note else scope

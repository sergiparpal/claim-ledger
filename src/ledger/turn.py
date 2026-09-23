"""Stop handler: the phase-1 pipeline, end to end.

Read the report the turn ended with, extract its claims in isolation, join them
against the evidence log, list the consequential actions the report never
mentioned, write the calibration rows, and put the appendix in front of the
user. One turn, one pass, no model anywhere but the extractor.

It never exits 2, for any reason. On Stop, exit 2 prevents Claude from stopping
and continues the conversation, which is precisely the gate, and the gate is
phase 2 (R-30). Every failure becomes an UNKNOWN turn that says so, because a
broken pipeline must never read as a clean one (I-9).

The order is deliberate:

- Capture first. The corpus is what phase 1 is measured against, and a report
  that failed to be audited is still a report worth annotating. An UNKNOWN turn
  keeps its capture.
- The join reads the whole session log, not this turn's slice: evidence from
  earlier turns of the same session is admissible (R-6). Coverage reads only
  the slice, because what a report left out is a question about this turn.
- The counter advances whatever happened, because a turn ended either way, and
  a number that did not move would have the next turn overwrite this one's
  capture. The recorder only reads that file; this is its one writer (R-5).
- The appendix goes out last, on stdout, as a systemMessage. It reaches the
  user and never the model's context: feeding it back would teach the agent
  which claims get caught.

The budget is the pipeline's own wall clock (R-43), and it is shorter than the
timeout the harness kills this process at. Everything slow runs inside what is
left of it — the model call, and the join, whose freshness scan shells out to
git — so that running out of time produces an UNKNOWN the user can see rather
than a hook that was killed mid-sentence.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path[0] = str(Path(__file__).resolve().parents[1])

from ledger import (appendix, budget, calibration, config, coverage,  # noqa: E402
                    evidence, extract, install, join, record, schema)

COMPONENT = "turn"
REPORTS = "reports"


class TurnError(Exception):
    """The Stop payload cannot be captured, or the turn cannot be audited."""


def main() -> int:
    """Hook entry point. Always returns 0, and never exits 2."""
    started = time.monotonic()
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
    except Exception as error:  # nothing can be captured, counted or audited
        record.report_failure(root, COMPONENT, raw, error, now)
        _say(appendix.render(appendix.Turn(unknown=_one_line(error))))
        return 0

    try:
        audited = audit(root, payload, session, number, raw, now, started)
    except Exception as error:  # the audit may not take the turn down with it
        record.report_failure(root, COMPONENT, raw, error, now)
        audited = appendix.Turn(unknown=_one_line(error))

    try:
        advance(counter, number)
    except Exception as error:
        record.report_failure(root, COMPONENT, raw, error, now)
        if audited.unknown is None:
            audited = dataclasses.replace(audited, unknown=_one_line(error))

    _say(appendix.render(audited))
    return 0


def audit(root: Path, payload: dict, session: str, number: int, raw: bytes,
          now: datetime, started: float) -> appendix.Turn:
    """The whole pipeline for one turn, as the appendix will show it."""
    cfg = config.load(root / config.CONFIG_FILENAME)
    clock = budget.Deadline(cfg.budget.turn_timeout_s, started=started)
    turn_id = _turn_id(payload)
    entries, unreadable = _read_log(evidence.session_log(root, session))
    mine = _slice(entries, turn_id, number)
    report = payload.get("last_assistant_message")
    report = report if isinstance(report, str) else ""

    if cfg.corpus.capture:
        capture(root, payload, session, number, now, mine, unreadable)

    # R-29 asks for this even when it is zero, and zero is when it says most.
    checks_seen = sum(1 for e in entries if e.record.get("kind") == "check")

    stopped = _stopped(root, session, cfg, unreadable)
    if stopped:
        for reason in stopped:
            record.report_failure(root, COMPONENT, raw, TurnError(reason), now)
        return appendix.Turn(checks_seen=checks_seen, unknown="; ".join(stopped))

    try:
        extraction = _extract(cfg, clock, report)
        judged = _join(entries, extraction.claims, cfg, root, clock)
        unreported = coverage.unreported(mine, [j.claim for j in judged],
                                         default_tier=cfg.default_tier)
        calibration.append(root, calibration.rows(
            judged, extraction.defects, session=session, turn_id=turn_id,
            turn_number=number, now=now))
    except Exception as error:
        record.report_failure(root, COMPONENT, raw, error, now)
        return appendix.Turn(checks_seen=checks_seen, unknown=_one_line(error))

    return appendix.Turn(judged=judged, unreported=unreported, checks_seen=checks_seen,
                         defects=extraction.defects)


def _extract(cfg: config.Config, clock: budget.Deadline, report: str) -> schema.Extraction:
    """The claims of the report, inside whatever the budget has left.

    An empty report is not sent anywhere: it asserts nothing, so it has no
    claims, and coverage still has everything to say about what the turn did
    without mentioning it (I-7). Its provenance names no route, because none
    answered.
    """
    if not report.strip():
        return schema.Extraction((), (), schema.Provenance("", "", "", ""))
    if clock.expired():
        raise TurnError(f"the {clock.seconds}s turn budget ran out before the model call")
    settings = dataclasses.replace(cfg.extractor,
                                   timeout_s=clock.bounded(cfg.extractor.timeout_s))
    return extract.extract(report, settings=settings)


def _join(entries, claims, cfg: config.Config, root: Path,
          clock: budget.Deadline) -> tuple[join.Judged, ...]:
    """The verdicts, bounded by the budget.

    The join has no model in it but it does read the working tree and shell out
    to git for the freshness test, and a repository large or slow enough would
    otherwise spend the margin that the UNKNOWN needs to be rendered in.
    """
    if clock.expired():
        raise TurnError(f"the {clock.seconds}s turn budget ran out before the join")
    return budget.run_within(clock.remaining(),
                             lambda: join.judge(claims, entries, cfg=cfg, root=root))


def _stopped(root: Path, session: str, cfg: config.Config,
             unreadable: str | None) -> list[str]:
    """Everything that makes this turn UNKNOWN before a verdict is even sought.

    The configuration hash is I-8: taken when the ledger first ran in this
    session and rechecked here, because the consequence table is the user's and
    a change to it is worth reporting whoever made it. A missing baseline is
    written rather than treated as a change: a session whose first tool call is
    this Stop has nothing to have changed from.

    An entry in errors.log means a record was lost, and a log with a hole in it
    cannot be joined against honestly — not for this turn and not for a later
    one in the same session, which is why the condition is the session's and
    not the turn's.
    """
    reasons = []
    digest = config.fingerprint(cfg.path)
    baseline = record.read_config_baseline(root, session)
    if baseline is None:
        record.seed_config_baseline(root, session, digest)
    elif baseline != digest:
        reasons.append(f"{config.CONFIG_FILENAME} changed during this session (I-8)")
    lost = _errors_seen(root, session)
    if lost:
        reasons.append(f"{lost} recorder failure{'s' if lost != 1 else ''} "
                       f"in this session: the evidence log has a hole in it")
    if unreadable is not None:
        reasons.append(f"the session log could not be read: {unreadable}")
    return reasons


def _errors_seen(root: Path, session: str) -> int:
    """How many lost evidence records this session has had (I-9).

    Recorder entries only. The spec says "any entry" because when it was
    written the recorder was the only thing that wrote to errors.log; now this
    handler writes there too, and counting its own entries would make one slow
    model call poison every remaining turn of the session — and compound,
    since each poisoned turn would log again. A failed audit is reported by the
    turn it happened in. A lost record is different: it leaves a hole in the
    log that every later join reads across, which is why that one is the
    session's condition and not the turn's.

    A line that cannot be parsed counts. Something wrote it, and the reader
    that must never be optimistic is this one.
    """
    try:
        text = (root / record.ERRORS_LOG).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return 0
    seen = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            seen += (entry.get("session") == session
                     and entry.get("component") == record.COMPONENT)
        except (ValueError, AttributeError):
            seen += 1
    return seen


def capture(root: Path, payload: dict, session: str, number: int, now: datetime,
            entries: list[evidence.Entry], unreadable: str | None) -> None:
    """Write reports/<session>-<n>.md, the corpus's raw material."""
    report = payload.get("last_assistant_message")
    header = {
        "session": session,
        "turn_number": number,
        "turn_id": _turn_id(payload),
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


def _turn_id(payload: dict) -> str | None:
    turn_id = payload.get("prompt_id")
    return turn_id if isinstance(turn_id, str) and turn_id else None


def _read_log(log: Path) -> tuple[list[evidence.Entry], str | None]:
    """Every record of the session, or an empty list and why it is empty."""
    try:
        return evidence.read(log), None
    except evidence.EvidenceError as e:
        return [], str(e)


def _slice(entries: list[evidence.Entry], turn_id: str | None,
           number: int) -> list[evidence.Entry]:
    """This turn's records, in file order.

    The prompt id picks the turn out when the harness gave one, since a missed
    Stop would leave two turns sharing a number; the count is what is left.
    """
    def mine(written):
        if turn_id is not None:
            return written.get("turn_id") == turn_id
        return written.get("turn_id") is None and written.get("turn_number") == number

    return [e for e in entries if mine(e.record)]


def _positions(entries: list[evidence.Entry]) -> str:
    """Each position on its own: a turn's records need not be contiguous."""
    return ",".join(str(entry.position) for entry in entries) if entries else "-"


def _one_line(error: BaseException) -> str:
    """A failure as the appendix shows it: one line, its type kept."""
    return f"{type(error).__name__}: {error}".splitlines()[0][:500]


def _say(message: str) -> None:
    """The appendix, to the user, through the only channel that reaches them."""
    sys.stdout.write(json.dumps({"systemMessage": message}) + "\n")
    sys.stdout.flush()


def _replace(path: Path, text: str) -> None:
    """Write the whole file through a rename, so a reader never sees half of it."""
    staged = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)


if __name__ == "__main__":
    sys.exit(main())

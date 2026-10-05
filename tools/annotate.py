#!/usr/bin/env python3
"""Annotate captured reports by hand into the corpus, one report at a time.

    python3 tools/annotate.py --by INITIALS [--older-than AGE] PROJECT [PROJECT ...]

Walks the reports the Stop handler captured under each
PROJECT/.claude/claim-ledger/reports/, skips those the corpus already holds,
and asks about the rest one sentence at a time: a key for each claim type,
Enter for a sentence that claims nothing, and spans typed by hand where one
sentence holds several claims or a claim is not a whole sentence. A finished
report is appended as one line, in the shape docs/SPEC.md § Corpus capture
gives. Quitting halfway through a report saves nothing of it.

The annotator is shown the report and nothing else. Not the extractor's
claims: the ones it missed are the ones recall exists to count, and an
annotator shown its list tends to confirm the list. Not the turn's evidence
either: what ran says nothing about what the report claims, and a passing
suite on screen makes a vague sentence read as a suite claim. Compare with
tools/extract_report.py afterwards, never before.

For the same reason, --older-than 1d (or 12h) leaves out the reports captured
more recently than that. The line at the end of a turn lists some of the claims
the extractor found, and a report annotated while that line is fresh in mind
is annotated against it. The recent ones are counted, and asked about in a
later run once they are old enough.

A span must appear in the report word for word, as the extractor's must. The
corpus is only ever appended to, and a file that cannot be appended to safely
stops the run before anything is asked: a line that is not an annotation, a
report annotated twice, or a last line with no line end, which the next
annotation would be written onto.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ledger import evidence, schema, turn  # noqa: E402

CORPUS = REPO / "corpus" / "annotations.jsonl"

#: One key per type, in the frozen vocabulary's own order.
KEYS = {str(number): kind for number, kind in enumerate(schema.CLAIM_TYPES, 1)}
LEGEND = "  ".join(f"{key} {kind}" for key, kind in KEYS.items())

# A list marker, a heading or a quote opening a line is layout, not the claim.
_MARKER = re.compile(r"(?:[-*+]|\d+[.)]|#{1,6}|>)\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


class AnnotateError(Exception):
    """The corpus or the reports cannot be read safely. Nothing is asked."""


class Quit(Exception):
    """The annotator stopped. The report in hand is not saved."""


class _Skip(Exception):
    """The annotator left this report for another run."""


@dataclasses.dataclass(frozen=True)
class Report:
    report_id: str  # the file's stem, <session>-<n>, which is what a corpus line names
    path: Path
    text: str       # the report exactly as captured, and nothing else of the file
    captured: datetime | None = None  # None when the header does not say, or not readably


@dataclasses.dataclass(frozen=True)
class Age:
    text: str  # as written, for the line that says what was left for later
    delta: timedelta


def age(text: str) -> Age:
    """12h or 2d: a whole, positive number of hours or of days."""
    match = re.fullmatch(r"([1-9]\d*)([hd])", text)
    if not match:
        raise argparse.ArgumentTypeError(f"{text!r} is not an age: write it as 12h or 2d")
    number = int(match.group(1))
    return Age(text, timedelta(hours=number) if match.group(2) == "h"
               else timedelta(days=number))


def annotated(corpus: Path) -> set[str]:
    """The report ids the corpus already holds. Refuses a file it cannot append to safely."""
    try:
        raw = corpus.read_bytes()
    except FileNotFoundError:
        return set()
    if raw and not raw.endswith(b"\n"):
        raise AnnotateError(f"{corpus}: the last line has no line end, and the next "
                            "annotation would be written onto it")
    try:
        lines = raw.decode("utf-8").split("\n")[:-1]
    except UnicodeDecodeError as e:
        raise AnnotateError(f"{corpus}: not UTF-8 ({e})") from e
    seen: dict[str, int] = {}
    for position, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except ValueError as e:
            raise AnnotateError(f"{corpus}:{position}: not a JSON line") from e
        report = entry.get("report") if isinstance(entry, dict) else None
        if not isinstance(report, str) or not report:
            raise AnnotateError(f"{corpus}:{position}: not an annotation, it names no report")
        if report in seen:
            raise AnnotateError(f"{corpus}:{position}: {report} is already annotated "
                                f"at line {seen[report]}")
        seen[report] = position
    return set(seen)


def find_reports(projects: Sequence[Path]) -> tuple[list[Report], list[str]]:
    """Every captured report under these projects, in turn order, and those that do not read."""
    reports: list[Report] = []
    unreadable: list[str] = []
    seen: dict[str, Path] = {}
    for project in projects:
        folder = project / evidence.STATE_DIR / turn.REPORTS
        if not folder.is_dir():
            raise AnnotateError(f"{project}: no captured reports, {folder} is not a directory")
        for path in sorted(folder.glob("*.md"), key=_turn_order):
            if path.stem in seen:
                raise AnnotateError(f"{path.stem} is captured twice: {seen[path.stem]} "
                                    f"and {path}")
            seen[path.stem] = path
            try:
                header, text = turn.read_capture(path)
            except (turn.TurnError, OSError, ValueError) as e:
                unreadable.append(f"{path}: {e}")
                continue
            reports.append(Report(path.stem, path, text, _captured(header)))
    return reports, unreadable


def _turn_order(path: Path) -> tuple[str, int]:
    """By session, then by turn number as a number, so that 10 comes after 9."""
    session, _, number = path.stem.rpartition("-")
    return (session, int(number)) if number.isdigit() else (path.stem, -1)


def _captured(header: Mapping[str, str]) -> datetime | None:
    """When the Stop handler captured the report, as the header's UTC timestamp says."""
    try:
        moment = datetime.fromisoformat(header.get("captured", ""))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def pieces(text: str) -> list[str]:
    """The report cut into sentences, each one a verbatim slice of it.

    Lines first, since bullets and paragraphs end claims as often as full stops
    do, then sentences within a line. A list marker, heading or quote opening
    a line is left out of the slice, and a code fence or anything with no
    letter or digit is not offered at all. A cut in the wrong place costs a
    keystroke, because a span typed by hand can cross it.
    """
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("```"):
            continue
        marker = _MARKER.match(line)
        if marker:
            line = line[marker.end():]
        for sentence in _SENTENCE_END.split(line):
            sentence = sentence.strip()
            if any(char.isalnum() for char in sentence):
                out.append(sentence)
    return out


def annotate_report(report: Report, *, ask: Callable[[str], str], out: TextIO,
                    place: str) -> list[dict] | None:
    """The claims of one report, as the annotator marks them. None leaves it for another run."""
    print(f"\n{place} · {report.report_id}\n{report.path}\n", file=out)
    print(report.text if report.text.strip() else "(the report is empty)", file=out)
    print(f"\n{LEGEND}\nEnter: not a claim   s: spans by hand   n: skip this report   "
          f"q: quit\n", file=out)
    sentences = pieces(report.text)
    while True:
        claims: list[dict] = []
        try:
            for index, sentence in enumerate(sentences, 1):
                print(f"[{index}/{len(sentences)}] {sentence}", file=out)
                claims += _sentence(sentence, report.text, ask=ask, out=out)
        except _Skip:
            return None
        print(f"\n{len(claims)} claims in {report.report_id}", file=out)
        for claim in claims:
            print(f"  {claim['type']:13} {claim['span']!r}", file=out)
        while True:
            answer = _key(ask, "Enter saves, r redoes this report, q quits without saving it: ")
            if answer == "":
                return claims
            if answer == "q":
                raise Quit
            if answer == "r":
                break
            print(f"  {answer!r} is not one of Enter, r or q", file=out)


def _sentence(sentence: str, text: str, *, ask: Callable[[str], str],
              out: TextIO) -> list[dict]:
    while True:
        answer = _key(ask, "> ")
        if answer in KEYS:
            return [{"span": sentence, "type": KEYS[answer]}]
        if answer == "":
            return []
        if answer == "s":
            return _by_hand(text, ask=ask, out=out)
        if answer == "n":
            raise _Skip
        if answer == "q":
            raise Quit
        print(f"  {answer!r} is not a key: {LEGEND}, Enter, s, n or q", file=out)


def _by_hand(text: str, *, ask: Callable[[str], str], out: TextIO) -> list[dict]:
    """Spans typed or pasted, each checked against the report. An empty span ends them."""
    claims = []
    while True:
        span = _read(ask, "  span (Enter when done): ").strip()
        if not span:
            return claims
        if span not in text:
            print("  not in the report word for word; copy it exactly", file=out)
            continue
        kind = _key(ask, "  type: ")
        while kind not in KEYS:
            print(f"  {kind!r} is not a type: {LEGEND}", file=out)
            kind = _key(ask, "  type: ")
        claims.append({"span": span, "type": KEYS[kind]})


def _key(ask: Callable[[str], str], prompt: str) -> str:
    return _read(ask, prompt).strip().lower()


def _read(ask: Callable[[str], str], prompt: str) -> str:
    try:
        return ask(prompt)
    except EOFError:
        raise Quit from None


def append(corpus: Path, entry: dict) -> None:
    """One annotation as one line, in a single write() on an O_APPEND descriptor.

    UTF-8 rather than the logs' ASCII: a person reads this file, and edits it
    when the corpus changes, and a span in any language but English would
    otherwise be a row of escapes.
    """
    data = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    corpus.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(corpus, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(fd, data)
    finally:
        os.close(fd)
    if written != len(data):
        raise AnnotateError(f"short write to {corpus}: {written} of {len(data)} bytes")


def main(argv: list[str], *, ask: Callable[[str], str] = input, out: TextIO | None = None,
         today: Callable[[], date] = date.today,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path,
                        help="project roots whose captured reports to annotate")
    parser.add_argument("--by", required=True,
                        help="the annotator's initials, written into every line")
    parser.add_argument("--older-than", type=age, metavar="AGE",
                        help="only reports captured at least this long ago, as 12h or 2d; "
                             "the rest are counted and left for a later run")
    parser.add_argument("--corpus", type=Path, default=CORPUS,
                        help="the file annotations are appended to "
                             "(default: corpus/annotations.jsonl in this repository)")
    args = parser.parse_args(argv[1:])
    if not args.by.strip() or args.by != args.by.strip():
        parser.error("--by takes the annotator's initials, without surrounding spaces")

    try:
        done = annotated(args.corpus)
        reports, unreadable = find_reports(args.projects)
    except AnnotateError as e:
        print(e, file=sys.stderr)
        return 2
    for problem in unreadable:
        print(f"left out, it does not read as a captured report: {problem}", file=sys.stderr)

    pending = [report for report in reports if report.report_id not in done]
    later = ""
    if args.older_than is not None:
        cutoff = now() - args.older_than.delta
        for report in pending:
            if report.captured is None:
                print(f"left out, it carries no capture time: {report.path}", file=sys.stderr)
        recent = [r for r in pending if r.captured is not None and r.captured > cutoff]
        pending = [r for r in pending if r.captured is not None and r.captured <= cutoff]
        later = f"; {len(recent)} captured in the last {args.older_than.text} left for later"
    print(f"{len(done)} annotated in {args.corpus}; {len(pending)} of {len(reports)} "
          f"captured reports still to do{later}", file=out)
    saved = 0
    for index, report in enumerate(pending, 1):
        try:
            claims = annotate_report(report, ask=ask, out=out,
                                     place=f"report {index} of {len(pending)}")
        except (Quit, KeyboardInterrupt):
            print(f"\nstopped: {saved} saved this run, nothing of {report.report_id}",
                  file=out)
            return 0
        if claims is None:
            print(f"left {report.report_id} for another run", file=out)
            continue
        try:
            append(args.corpus, {"report": report.report_id, "annotated": today().isoformat(),
                                 "by": args.by, "claims": claims})
        except (AnnotateError, OSError) as e:
            print(e, file=sys.stderr)
            return 2
        saved += 1
        print(f"saved {report.report_id}", file=out)
    print(f"\n{saved} saved this run", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

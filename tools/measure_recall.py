#!/usr/bin/env python3
"""Score the extractor against the annotated corpus, and the annotator against its anchor.

    python3 tools/measure_recall.py agreement [--root PROJECT] [--anchor PATH]
                                              [--corpus PATH] [--spans]
    python3 tools/measure_recall.py recall [--root PROJECT] [--anchor PATH] [--corpus PATH]
                                           [--spans] RUN.jsonl [RUN.jsonl ...]

Both set one side's claims against a reference as SPEC § Corpus capture
measures recall: a claim is found when the other side typed a sentence holding
it the same way. The sentences are those ledger.sentences cuts, the ones the
extractor is asked about and the annotators are shown. A claim given by its
span is held by the sentences the span is, failing those by the ones it is
part of, and failing those by the ones it overlaps, since a span typed by hand
can cross a cut. A claim of the reference that the other side typed no
sentence of alike is a miss; a claim of the other side that matches none of
the reference's is spurious.

`agreement` sets the model's annotations in --corpus (default
corpus/annotations.jsonl) against the reports a person annotated by hand in
--anchor (default corpus/anchor.jsonl): how many of the person's checkable
claims the annotator found, how many of the annotator's the person made, and
every sentence the two typed differently. Only reports the person has
finished are read, so nothing the model said about a report still to be
annotated by hand is shown.

`recall` scores runs of tools/measure_route.py made with --corpus, one file to
a candidate route, against --corpus. For each pass it gives recall on
checkable claims, over every answer the pass got, a late one included; the
share of everything extracted, of every type, that is spurious, split into
claims in sentences the annotator left unmarked and claims in sentences it
typed otherwise; the sentence numbers that named no sentence; the share of
turns the hook would have left UNKNOWN, with no answer or with one after the
route's own deadline; and the share of checkable claims whose referents the
join could match at all. A candidate is judged by its worst pass on each,
beside the threshold of REQUIREMENTS § Rollout phases and the annotator's
agreement with the anchor, and every claim a pass missed is listed with the
passes that missed it.

A line names a report, a sentence number and types; --spans prints the
sentence under it. Nothing here makes a call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import astuple, dataclass, field
from pathlib import Path
from typing import TextIO

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

import annotate  # noqa: E402
from ledger import schema, sentences  # noqa: E402

ANCHOR = REPO / "corpus" / "anchor.jsonl"
CHECKABLE = schema.CHECKABLE_TYPES
#: REQUIREMENTS § Rollout phases, declared 20 September 2026: recall 0.90 or
#: better on checkable claims over at least 50 reports, spurious extractions at
#: or below 0.10 of everything extracted, and no span the report does not hold,
#: which under the sentence contract is a sentence number naming no sentence.
RECALL_AT_LEAST, SPURIOUS_AT_MOST, REPORTS_AT_LEAST = 0.90, 0.10, 50
PASSES = 3   # SPEC § Corpus capture: each candidate runs the corpus three times


class MeasureError(Exception):
    """A file cannot be scored as it stands, and nothing is measured from it."""


@dataclass(frozen=True)
class Annotation:
    """One report's line of a corpus file."""

    report: str
    by: str
    claims: tuple[tuple[str, str], ...]   # (span, type), as written


@dataclass(frozen=True)
class Marked:
    """A claim as the comparison sees it: the sentences that hold it, and its type."""

    sentences: frozenset[int]
    type: str


@dataclass(frozen=True)
class Tally:
    """One side against a reference, summed over reports."""

    checkable: int = 0   # the reference's checkable claims
    found: int = 0       # those the other side typed a sentence of alike
    extracted: int = 0   # the other side's claims, of every type
    unmarked: int = 0    # of those, matching none, in a sentence the reference left unmarked
    retyped: int = 0     # of those, matching none, in a sentence the reference typed otherwise

    def __add__(self, other: Tally) -> Tally:
        return Tally(*(mine + theirs for mine, theirs in zip(astuple(self), astuple(other))))

    @property
    def recall(self) -> float | None:
        return self.found / self.checkable if self.checkable else None

    @property
    def spurious(self) -> float | None:
        return (self.unmarked + self.retyped) / self.extracted if self.extracted else None


@dataclass
class Pass:
    """One pass of a candidate over the corpus, scored."""

    number: int
    asked: set[str] = field(default_factory=set)
    no_answer: set[str] = field(default_factory=set)
    late: int = 0          # answered, after the route's own deadline
    empty: int = 0         # answered with nothing, where the annotator found claims
    defects: int = 0
    tally: Tally = field(default_factory=Tally)
    usable: list[int] = field(default_factory=lambda: [0, 0])  # checkable claims, matchable
    missed: list[tuple[str, Marked]] = field(default_factory=list)

    @property
    def unknown(self) -> int:
        return len(self.no_answer) + self.late


def read(corpus: Path) -> dict[str, Annotation]:
    """The annotations a corpus file holds, by report; none when there is no file."""
    annotate.annotated(corpus)               # one well-formed line per report, or it raises
    try:
        lines = corpus.read_text(encoding="utf-8").split("\n")[:-1]
    except FileNotFoundError:
        return {}
    held = {}
    for position, line in enumerate(lines, 1):
        entry = json.loads(line)
        claims = entry.get("claims")
        if not isinstance(claims, list) or not all(
                isinstance(claim, dict) and isinstance(claim.get("span"), str)
                and claim["span"].strip() and claim.get("type") in schema.CLAIM_TYPES
                for claim in claims):
            raise MeasureError(f"{corpus}:{position}: its claims are not spans, each with a "
                               f"type of the vocabulary")
        held[entry["report"]] = Annotation(entry["report"], str(entry.get("by")),
                                           tuple((c["span"], c["type"]) for c in claims))
    return held


def digest(path: Path) -> str:
    """The file a figure was measured against, named by what it holds."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def holding(span: str, text: str, cut: Sequence[str]) -> frozenset[int]:
    """The numbers of the sentences that hold a span: the ones it is, failing those
    the ones it is part of, and failing those the ones it overlaps in the report."""
    whole = frozenset(n for n, sentence in enumerate(cut, 1) if sentence == span)
    if whole:
        return whole
    within = frozenset(n for n, sentence in enumerate(cut, 1) if span in sentence)
    if within:
        return within
    places, at = [], 0
    for sentence in cut:                      # each one a slice of the report, in order
        start = text.index(sentence, at)
        places.append((start, start + len(sentence)))
        at = start + len(sentence)
    crossed: set[int] = set()
    start = text.find(span)
    while start != -1:
        end = start + len(span)
        crossed |= {n for n, (first, last) in enumerate(places, 1) if first < end and start < last}
        start = text.find(span, start + 1)
    return frozenset(crossed)


def marked(annotation: Annotation, text: str, cut: Sequence[str], where: Path) -> list[Marked]:
    """An annotation's claims, each with the sentences that hold it."""
    claims = []
    for span, kind in annotation.claims:
        held = holding(span.strip(), text, cut)
        if not held:
            raise MeasureError(f"{where}: a claim of {annotation.report} is in none of its "
                               f"sentences; the report or its cut has changed since")
        claims.append(Marked(held, kind))
    return claims


def score(reference: Sequence[Marked], other: Sequence[Marked]) -> tuple[Tally, list[Marked]]:
    """The other side against the reference on one report, and the reference's
    checkable claims it missed."""
    def alike(one: Marked, another: Marked) -> bool:
        return one.type == another.type and bool(one.sentences & another.sentences)

    checkable = [claim for claim in reference if claim.type in CHECKABLE]
    missed = [claim for claim in checkable if not any(alike(claim, o) for o in other)]
    unmatched = [o for o in other if not any(alike(o, claim) for claim in reference)]
    marked_at = frozenset().union(*(claim.sentences for claim in reference))
    unmarked = sum(1 for o in unmatched if not o.sentences & marked_at)
    return Tally(len(checkable), len(checkable) - len(missed), len(other), unmarked,
                 len(unmatched) - unmarked), missed


def anchored(anchor: Mapping[str, Annotation], corpus: Mapping[str, Annotation],
             texts: Mapping[str, str], where: tuple[Path, Path]
             ) -> list[tuple[str, list[str], list[Marked], list[Marked]]]:
    """Each report annotated both by hand and by the model: its id, its sentences,
    the person's claims and the annotator's."""
    pairs = []
    for report in sorted(set(anchor) & set(corpus)):
        text = _text(report, texts, where[0])
        cut = sentences.split(text)
        pairs.append((report, cut, marked(anchor[report], text, cut, where[0]),
                      marked(corpus[report], text, cut, where[1])))
    return pairs


def agree(pairs: Iterable[tuple[str, list[str], list[Marked], list[Marked]]]
          ) -> tuple[Tally, Tally]:
    """The annotator against the person, and the person against the annotator."""
    pairs = list(pairs)
    return (sum((score(by_hand, model)[0] for _, _, by_hand, model in pairs), Tally()),
            sum((score(model, by_hand)[0] for _, _, by_hand, model in pairs), Tally()))


def scored(path: Path, reference: Mapping[str, list[Marked]],
           cuts: Mapping[str, list[str]]) -> tuple[dict, list[Pass]]:
    """A run file's route, and each of its passes scored against the corpus."""
    route, by_pass = _passes(path)
    passes = []
    for number, rows in by_pass.items():
        done = Pass(number)
        for row in rows:
            report = row.get("report")
            if report not in reference:
                continue                     # the corpus does not hold it now
            if report in done.asked:
                raise MeasureError(f"{path}: pass {number} asked about {report} twice; "
                                   f"one run to a file")
            done.asked.add(report)
            if row.get("outcome") != "usable":
                done.no_answer.add(report)
                continue
            done.late += row["wall"] > route["timeout_s"]
            answer = _answer(row, cuts[report], path)
            tally, missed = score(reference[report], answer)
            done.tally += tally
            done.missed += [(report, claim) for claim in missed]
            done.empty += not answer and bool(reference[report])
            done.defects += row.get("defects") or 0
            for claims, matched in (row.get("usable") or {}).values():
                done.usable[0] += claims
                done.usable[1] += matched
        passes.append(done)
    return route, passes


def judged(passes: Sequence[Pass], reports: int) -> tuple[dict, list[str]]:
    """A candidate's worst pass on each figure, and how it falls short of phase 1."""
    recalls = [p.tally.recall for p in passes if p.tally.recall is not None]
    spurious = [p.tally.spurious for p in passes if p.tally.spurious is not None]
    worst = {"recall": min(recalls, default=None), "spurious": max(spurious, default=None),
             "unknown": max((p.unknown / len(p.asked) for p in passes if p.asked), default=None),
             "defects": sum(p.defects for p in passes)}
    short = []
    if reports < REPORTS_AT_LEAST:
        short.append(f"the corpus holds {reports} reports, under {REPORTS_AT_LEAST}")
    if len(passes) < PASSES:
        short.append(f"{len(passes)} of the {PASSES} passes SPEC asks for")
    short += [f"pass {p.number} asked about {len(p.asked)} of the corpus's {reports} reports"
              for p in passes if len(p.asked) < reports]
    if worst["recall"] is None:
        short.append("no recall could be measured")
    elif worst["recall"] < RECALL_AT_LEAST:
        short.append(f"recall {worst['recall']:.2f} is under {RECALL_AT_LEAST:.2f}")
    if worst["spurious"] is not None and worst["spurious"] > SPURIOUS_AT_MOST:
        short.append(f"spurious {worst['spurious']:.2f} is over {SPURIOUS_AT_MOST:.2f}")
    if worst["defects"]:
        short.append(f"{worst['defects']} sentence numbers named no sentence")
    return worst, short


def agreement(args, out: TextIO) -> int:
    anchor, corpus = read(args.anchor), read(args.corpus)
    if not anchor:
        print(f"{args.anchor} holds no report annotated by hand yet", file=out)
        return 1
    for report in sorted(set(anchor) - set(corpus)):
        print(f"{report} is in the anchor, and the model has not annotated it", file=sys.stderr)
    pairs = anchored(anchor, corpus, _texts(args.root), (args.anchor, args.corpus))
    if not pairs:
        print("the model has annotated none of the anchor's reports", file=out)
        return 1
    annotator, person = agree(pairs)
    reports = [report for report, *_ in pairs]
    print(f"{args.anchor}: {len(pairs)} reports, sha256 {digest(args.anchor)}, "
          f"by {_signed(anchor, reports)}", file=out)
    print(f"{args.corpus}: by {_signed(corpus, reports)}", file=out)
    print(f"  the annotator found {annotator.found} of the person's {annotator.checkable} "
          f"checkable claims ({_two(annotator.recall)})", file=out)
    print(f"  the person made {person.found} of the annotator's {person.checkable} "
          f"checkable claims ({_two(person.recall)})", file=out)
    print(f"  of the annotator's {annotator.extracted} claims of every type, "
          f"{annotator.unmarked + annotator.retyped} ({_two(annotator.spurious)}) are not "
          f"the person's: {annotator.unmarked} in sentences the person left unmarked, "
          f"{annotator.retyped} in sentences the person typed otherwise", file=out)
    print("by report:", file=out)
    differing = []
    for report, cut, by_hand, model in pairs:
        found, _ = score(by_hand, model)
        made, _ = score(model, by_hand)
        print(f"  {report}  {len(cut)} sentences, {len(by_hand)} claims by hand and "
              f"{len(model)} by the annotator; found {found.found} of {found.checkable}, "
              f"made {made.found} of {made.checkable}", file=out)
        for number, sentence in enumerate(cut, 1):
            mine, theirs = _types_at(by_hand, number), _types_at(model, number)
            if mine != theirs:
                differing.append((report, number, mine, theirs, sentence))
    print(f"{len(differing)} sentences typed differently" + (":" if differing else ""),
          file=out)
    for report, number, mine, theirs, sentence in differing:
        print(f"  {report} [{number}] by hand {mine}; annotator {theirs}", file=out)
        if args.spans:
            print(f"      {sentence}", file=out)
    return 0


def recall(args, out: TextIO) -> int:
    corpus = read(args.corpus)
    if not corpus:
        raise MeasureError(f"{args.corpus} annotates no report")
    texts = _texts(args.root)
    cuts, reference = {}, {}
    for report, annotation in corpus.items():
        text = _text(report, texts, args.corpus)
        cuts[report] = sentences.split(text)
        reference[report] = marked(annotation, text, cuts[report], args.corpus)
    anchor = read(args.anchor)
    pairs = anchored(anchor, corpus, texts, (args.anchor, args.corpus))
    candidates = [(path, *scored(path, reference, cuts)) for path in args.runs]
    print(f"{args.corpus}: {len(corpus)} reports, sha256 {digest(args.corpus)}, "
          f"by {_signed(corpus, corpus)}", file=out)
    if pairs:
        annotator, person = agree(pairs)
        print(f"anchor: {len(pairs)} reports by {_signed(anchor, [p[0] for p in pairs])}, "
              f"sha256 {digest(args.anchor)}: the annotator found {annotator.found} of the "
              f"person's {annotator.checkable} checkable claims ({_two(annotator.recall)}), "
              f"and the person made {person.found} of the annotator's {person.checkable} "
              f"({_two(person.recall)})", file=out)
    else:
        where = (f"none of the reports of {args.anchor} is in the corpus" if anchor
                 else f"no report in {args.anchor} yet")
        print(f"anchor: {where}, so the annotator these figures agree with has not been "
              f"checked against a person", file=out)
    for path, route, passes in candidates:
        print(f"\n{path}: {route.get('model')} via {route.get('provider')}, prompt "
              f"{route.get('prompt')}, deadline {route['timeout_s']:g}s", file=out)
        for p in passes:
            _print_pass(p, route["timeout_s"], out)
        worst, short = judged(passes, len(corpus))
        print(f"  worst pass: recall {_two(worst['recall'])}, spurious "
              f"{_two(worst['spurious'])}, UNKNOWN {_percent(worst['unknown'])}, "
              f"{worst['defects']} defects", file=out)
        print("  clears the phase-1 threshold" if not short else
              "  does not clear the phase-1 threshold: " + "; ".join(short), file=out)
    for path, _, passes in candidates:
        _print_misses(path, passes, cuts, args.spans, out)
    return 0


def _print_pass(p: Pass, deadline: float, out: TextIO) -> None:
    t = p.tally
    print(f"  pass {p.number}  recall {_two(t.recall)}: {t.found} of {t.checkable} checkable "
          f"claims found, in {len(p.asked) - len(p.no_answer)} answers, {p.empty} of them "
          f"empty", file=out)
    print(f"          spurious {_two(t.spurious)}: {t.unmarked + t.retyped} of {t.extracted} "
          f"claims extracted, {t.unmarked} in unmarked sentences, {t.retyped} typed otherwise",
          file=out)
    print(f"          UNKNOWN {p.unknown} of {len(p.asked)} turns "
          f"({_percent(p.unknown / len(p.asked) if p.asked else None)}): "
          f"{len(p.no_answer)} without an answer, {p.late} after {deadline:g}s; "
          f"{p.defects} defects", file=out)
    claims, matched = p.usable
    print(f"          referents the join could match: {matched} of {claims} checkable claims "
          f"({_percent(matched / claims if claims else None)})", file=out)


def _print_misses(path: Path, passes: Sequence[Pass], cuts: Mapping[str, list[str]],
                  spans: bool, out: TextIO) -> None:
    missed: dict[tuple[str, tuple[int, ...], str], list[int]] = defaultdict(list)
    for p in passes:
        for report, claim in p.missed:
            missed[(report, tuple(sorted(claim.sentences)), claim.type)].append(p.number)
    print(f"\n{path}: {len(missed)} checkable claims missed in at least one pass", file=out)
    for (report, numbers, kind), by in sorted(missed.items()):
        unanswered = [p.number for p in passes if report in p.no_answer]
        print(f"  {report} [{', '.join(map(str, numbers))}] {kind}: missed in "
              f"pass{'es' if len(by) > 1 else ''} {', '.join(map(str, by))}"
              + (f"; no answer in pass{'es' if len(unanswered) > 1 else ''} "
                 f"{', '.join(map(str, unanswered))}" if unanswered else ""), file=out)
        if spans:
            for number in numbers:
                print(f"      {cuts[report][number - 1]}", file=out)


def _passes(path: Path) -> tuple[dict, dict[int, list[dict]]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line]
    except ValueError as e:
        raise MeasureError(f"{path}: not a run file ({e})") from e
    asked = [row for row in rows if isinstance(row, dict) and row.get("pass")]
    if not asked:
        raise MeasureError(f"{path}: no pass over captured reports")
    if any(row.get("outcome") == "usable" and "answer" not in row for row in asked):
        raise MeasureError(f"{path}: its answers were not kept; make the run with --corpus")
    if len({json.dumps(row.get("route"), sort_keys=True) for row in asked}) > 1:
        raise MeasureError(f"{path}: its rows name more than one route, and a run file is "
                           f"one candidate")
    route = asked[0].get("route")
    if not isinstance(route, dict) or not isinstance(route.get("timeout_s"), (int, float)):
        raise MeasureError(f"{path}: its rows do not name the route that answered them")
    by_pass: dict[int, list[dict]] = defaultdict(list)
    for row in asked:
        by_pass[row["pass"]].append(row)
    return route, dict(sorted(by_pass.items()))


def _answer(row: Mapping, cut: Sequence[str], path: Path) -> list[Marked]:
    """A kept answer's claims, checked against the report as it is cut now."""
    if row.get("sentences") != len(cut):
        raise MeasureError(f"{path}: {row['report']} is cut into {len(cut)} sentences now, "
                           f"and was cut into {row.get('sentences')} when it was asked")
    answer = row["answer"]
    if not isinstance(answer, list) or not all(
            isinstance(item, list) and len(item) == 2 and isinstance(item[0], int)
            and 1 <= item[0] <= len(cut) and item[1] in schema.CLAIM_TYPES for item in answer):
        raise MeasureError(f"{path}: the answer kept for {row['report']} is not sentence "
                           f"numbers and types")
    return [Marked(frozenset({number}), kind) for number, kind in answer]


def _texts(root: Path) -> dict[str, str]:
    reports, _ = annotate.find_reports([root])
    return {report.report_id: report.text for report in reports}


def _text(report: str, texts: Mapping[str, str], where: Path) -> str:
    if report not in texts:
        raise MeasureError(f"{where}: {report} is not captured under the project")
    return texts[report]


def _types_at(claims: Sequence[Marked], number: int) -> str:
    kinds = sorted({claim.type for claim in claims if number in claim.sentences})
    return " + ".join(kinds) or "none"


def _signed(entries: Mapping[str, Annotation], reports: Iterable[str]) -> str:
    signed = Counter(entries[report].by for report in reports)
    if len(signed) == 1:
        return next(iter(signed))
    return ", ".join(f"{by} ({count})" for by, count in signed.most_common())


def _two(share: float | None) -> str:
    return "-" if share is None else f"{share:.2f}"


def _percent(share: float | None) -> str:
    return "-" if share is None else f"{share:.0%}"


def main(argv: list[str], *, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def common(sub):
        sub.add_argument("--root", type=Path, default=Path("."),
                         help="project whose captured reports the corpus annotates")
        sub.add_argument("--anchor", type=Path, default=ANCHOR,
                         help="the reports annotated by hand "
                              "(default: corpus/anchor.jsonl in this repository)")
        sub.add_argument("--corpus", type=Path, default=annotate.CORPUS,
                         help="the model's annotations "
                              "(default: corpus/annotations.jsonl in this repository)")
        sub.add_argument("--spans", action="store_true",
                         help="print the sentence under each line that names one")

    common(commands.add_parser("agreement", help="the annotator against the anchor"))
    runs = commands.add_parser("recall", help="runs of measure_route.py against the corpus")
    common(runs)
    runs.add_argument("runs", type=Path, nargs="+",
                      help="files of measure_route.py run --corpus, one to a candidate")
    args = parser.parse_args(argv[1:])
    try:
        return {"agreement": agreement, "recall": recall}[args.command](args, out)
    except (MeasureError, annotate.AnnotateError, OSError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

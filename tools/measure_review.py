#!/usr/bin/env python3
"""Measure a review step: a second call that may drop claims from stored answers.

    python3 tools/measure_review.py run --run RUN.jsonl --pass N [--root PROJECT]
                                        [--config ROUTE.toml] [--prompt PROMPT.md]
                                        [--corpus CORPUS.jsonl] [--only REPORTS.txt]
                                        [--limit N] [--deadline S] OUT.jsonl
    python3 tools/measure_review.py score --run RUN.jsonl --pass N [--root PROJECT]
                                          [--corpus CORPUS.jsonl] OUT.jsonl

docs/precision-step.md says what the step is and why it is measured this way:
on answers a corpus run already kept, so that only the review is new and no
report is extracted again.

`run` sends each usable answer of pass N of RUN, on a report CORPUS annotates,
to the route of PROJECT/claim-ledger.toml, or of --config, with the review
prompt (--prompt, by default src/ledger/prompts/review-2.md): the report cut
and numbered as the extractor reads it, then the answer's claims one a line,
"c<i>: [<sentence>] <type> | <the sentence>". The reply gives each claim a
verdict, keep or drop, in a shape the endpoint is held to; nothing is added and
nothing is retyped. The call is made as the hook makes one, with the client's
single retry, under a wall clock of --deadline seconds (default 60) so that a
slow review is timed rather than cut off. A row holds the report's id, the
pass, the prompt's version, how many claims there were, which ones were
dropped, how long the call took and what it cost, and no text of the report.
A report OUT already holds is skipped, so a run stopped halfway resumes.

`score` sets the pass before and after the review against CORPUS, as
tools/measure_recall.py scores a run: recall on checkable claims, the spurious
share of everything kept, what was found by type, what the review dropped and
whether the reference makes it, and how long the reviews took. It makes no call.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

import measure_recall  # noqa: E402
from ledger import config, extract, schema, sentences  # noqa: E402

PROMPT_PATH = REPO / "src" / "ledger" / "prompts" / "review-2.md"
DEADLINE_S = 60.0
PAUSE_S = 1.0          # between calls, as tools/measure_route.py paces a run
MAX_TOKENS = 4096      # a verdict for each of a long report's claims fits well inside
#: The hook's own deadline for the extractor, against which a review's time is read.
HOOK_DEADLINE_S = 20.0

#: The reply: one verdict per claim, naming it as the request named it.
SCHEMA = {"type": "object",
          "properties": {"verdicts": {"type": "array", "items": {
              "type": "object",
              "properties": {"claim": {"type": "string"}, "keep": {"type": "boolean"}},
              "required": ["claim", "keep"], "additionalProperties": False}}},
          "required": ["verdicts"], "additionalProperties": False}


class ReviewError(Exception):
    """A reply that cannot be read as verdicts on the claims it was sent."""


def claim_lines(cut: Sequence[str], claims: Sequence[measure_recall.Marked]) -> str:
    """The claims as the reviewer reads them, each with its sentence repeated."""
    lines = []
    for number, claim in enumerate(claims, 1):
        sentence = min(claim.sentences)
        lines.append(f"c{number}: [{sentence}] {claim.type} | {cut[sentence - 1]}")
    return "\n".join(lines) or "(none)"


def build_request(cut: Sequence[str], claims: Sequence[measure_recall.Marked], *,
                  settings: config.Extractor, prompt: extract.Prompt) -> extract.Request:
    """The review call: the report and an answer about it, and nothing else (I-1).

    It goes to the route the extractor uses, with the same pin, no fallbacks and
    no training on the report, and its reply is held to SCHEMA.
    """
    types = "\n".join(f"- {name}" for name in schema.CLAIM_TYPES)
    body = {
        "model": settings.model, "max_tokens": MAX_TOKENS, **dict(settings.parameters),
        "system": f"{prompt.text}\n\nThe types, and nothing else:\n{types}",
        "messages": [{"role": "user", "content": sentences.numbered(cut)
                      + "\n\nThe other reader's claims:\n" + claim_lines(cut, claims)}],
        "provider": {"order": [settings.provider], "allow_fallbacks": False,
                     "data_collection": "deny", "require_parameters": True},
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }
    return extract.Request(url=settings.base_url.rstrip("/") + extract.API_PATH, body=body,
                           auth=settings.auth, key_env=settings.key_env, prefilled=False)


def verdicts(body: bytes, count: int) -> tuple[list[int], int]:
    """The claims a reply drops, by number, and how many it gave no verdict.

    A claim with no verdict is kept: the step may only shorten the list, and
    one it did not judge is left as the extractor gave it. A verdict on a claim
    that was not sent, or a reply that is not verdicts, makes the review
    unusable rather than guessed at.
    """
    try:
        envelope = json.loads(body)
        text = "".join(block.get("text") or "" for block in envelope.get("content") or []
                       if isinstance(block, dict) and block.get("type") == "text")
        given = json.loads(text)["verdicts"]
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ReviewError(f"the reply is not verdicts: {type(e).__name__}") from e
    names = {f"c{number}": number for number in range(1, count + 1)}
    if not isinstance(given, list) or not all(
            isinstance(v, dict) and v.get("claim") in names and isinstance(v.get("keep"), bool)
            for v in given):
        raise ReviewError("a verdict names no claim that was sent, or says neither keep nor drop")
    seen: dict[int, bool] = {}
    for verdict in given:
        seen.setdefault(names[verdict["claim"]], verdict["keep"])
    return sorted(number for number, keep in seen.items() if not keep), count - len(seen)


def review_row(report: str, cut: Sequence[str], claims: Sequence[measure_recall.Marked], *,
               settings: config.Extractor, prompt: extract.Prompt, number: int,
               transport: Callable[[extract.Request, float], extract.Response],
               deadline: float) -> dict:
    """One review, and what it cost. A failure becomes the row, never an exception."""
    row = {"report": report, "pass": number, "prompt": prompt.version,
           "route": {"model": settings.model, "provider": settings.provider},
           "claims": len(claims)}
    request = build_request(cut, claims, settings=settings, prompt=prompt)
    started = time.monotonic()
    try:
        response = extract._send(transport, request, deadline)
        envelope = json.loads(response.body)
        row["usage"] = {k: v for k, v in (envelope.get("usage") or {}).items()
                        if isinstance(v, (int, float))}
        row["blocks"] = [b.get("type") for b in envelope.get("content") or []
                         if isinstance(b, dict)]
        drop, missing = verdicts(response.body, len(claims))
        row.update(outcome="usable", drop=drop, missing=missing)
    except ReviewError as e:
        row.update(outcome="unusable", error=str(e)[:200])
    except (extract.ExtractError, ValueError) as e:
        row.update(outcome="failed", error=str(e)[:200])
    row["wall"] = round(time.monotonic() - started, 3)
    return row


def run(args, *, transport=extract.https_transport, out: TextIO = sys.stdout,
        pause: float = PAUSE_S) -> int:
    settings = config.load(args.config or args.root / config.CONFIG_FILENAME).extractor
    prompt = extract.load_prompt(args.prompt or PROMPT_PATH)
    corpus = measure_recall.read(args.corpus)
    texts = measure_recall._texts(args.root)
    _, by_pass = measure_recall._passes(args.run)
    if args.number not in by_pass:
        raise SystemExit(f"{args.run} has no pass {args.number}")
    done = {json.loads(line)["report"] for line in args.out.read_text(encoding="utf-8").splitlines()
            if line} if args.out.exists() else set()
    only = set(args.only.read_text(encoding="utf-8").split()) if args.only else None
    rows = [row for row in by_pass[args.number]
            if row.get("report") in corpus and row.get("outcome") == "usable"
            and row["report"] not in done and (only is None or row["report"] in only)]
    rows = rows[:args.limit] if args.limit else rows
    print(f"{prompt.version}, {settings.model} via {settings.provider}; pass {args.number} "
          f"of {args.run.name}: {len(rows)} answers to review", file=out)
    for index, row in enumerate(rows, 1):
        report = row["report"]
        cut = sentences.split(measure_recall._text(report, texts, args.run))
        claims = measure_recall._answer(row, cut, args.run)
        result = review_row(report, cut, claims, settings=settings, prompt=prompt,
                            number=args.number, transport=transport, deadline=args.deadline)
        with args.out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
        print(f"{index:3}/{len(rows)} {report[:12]} claims {len(claims):3} drop "
              f"{len(result.get('drop') or []):3} {result['outcome']:9} {result['wall']:.1f}s"
              + (f" {result['error']}" if result.get("error") else ""), file=out, flush=True)
        if pause and index < len(rows):
            time.sleep(pause)
    return 0


def tallies(reference: Sequence[measure_recall.Marked], claims: Sequence[measure_recall.Marked],
            drop: Sequence[int]) -> tuple[measure_recall.Tally, measure_recall.Tally]:
    """One report scored before the review and after it."""
    kept = [claim for number, claim in enumerate(claims, 1) if number not in set(drop)]
    return measure_recall.score(reference, claims)[0], measure_recall.score(reference, kept)[0]


def score(args, *, out: TextIO = sys.stdout) -> int:
    corpus = measure_recall.read(args.corpus)
    texts = measure_recall._texts(args.root)
    _, by_pass = measure_recall._passes(args.run)
    reviews = {}
    for line in args.out.read_text(encoding="utf-8").splitlines():
        if line:
            entry = json.loads(line)
            reviews[entry["report"]] = entry
    before, after = measure_recall.Tally(), measure_recall.Tally()
    found = Counter()
    dropped = Counter()
    outcomes = Counter(entry.get("outcome") for entry in reviews.values())
    for row in by_pass.get(args.number, []):
        report = row.get("report")
        review = reviews.get(report)
        if report not in corpus or row.get("outcome") != "usable" or not review \
                or review.get("outcome") != "usable":
            continue
        text = measure_recall._text(report, texts, args.run)
        cut = sentences.split(text)
        reference = measure_recall.marked(corpus[report], text, cut, args.corpus)
        claims = measure_recall._answer(row, cut, args.run)
        drop = set(review.get("drop") or [])
        one, two = tallies(reference, claims, sorted(drop))
        before += one
        after += two
        kept = [claim for number, claim in enumerate(claims, 1) if number not in drop]
        for kind in schema.CHECKABLE_TYPES:
            sub = [claim for claim in reference if claim.type == kind]
            found[(kind, "before")] += measure_recall.score(sub, claims)[0].found
            found[(kind, "after")] += measure_recall.score(sub, kept)[0].found
            found[(kind, "of")] += len(sub)
        marked_at = frozenset().union(*(claim.sentences for claim in reference))
        for number, claim in enumerate(claims, 1):
            if number in drop:
                hit = any(claim.type == r.type and claim.sentences & r.sentences for r in reference)
                where = ("matched the reference" if hit else "in a sentence the reference "
                         "leaves unmarked" if not claim.sentences & marked_at else
                         "typed otherwise than the reference")
                dropped[("checkable" if claim.type in schema.CHECKABLE_TYPES
                         else "judgment or intent", where)] += 1
    usable = [entry for entry in reviews.values() if entry.get("outcome") == "usable"]
    walls = sorted(entry["wall"] for entry in usable)
    cost = sum((entry.get("usage") or {}).get("cost") or 0 for entry in reviews.values())
    print(f"pass {args.number} of {args.run.name} against {args.corpus.name} "
          f"{measure_recall.digest(args.corpus)}; reviews {dict(outcomes)}", file=out)
    for label, tally in (("before the review", before), ("after it", after)):
        print(f"  {label}: recall {tally.found}/{tally.checkable} = {tally.recall:.3f}, spurious "
              f"{tally.unmarked + tally.retyped}/{tally.extracted} = {tally.spurious:.3f}", file=out)
    print("  found, before and after: " + ", ".join(
        f"{kind} {found[(kind, 'before')]} and {found[(kind, 'after')]} of {found[(kind, 'of')]}"
        for kind in schema.CHECKABLE_TYPES), file=out)
    for (kind, where), count in sorted(dropped.items()):
        print(f"  dropped, {kind}, {where}: {count}", file=out)
    if walls:
        print(f"  a review took {statistics.median(walls):.1f}s at the median, "
              f"{walls[int(0.95 * (len(walls) - 1))]:.1f}s at the 95th percentile and "
              f"{walls[-1]:.1f}s at the most; {sum(w > HOOK_DEADLINE_S for w in walls)} of "
              f"{len(walls)} passed {HOOK_DEADLINE_S:.0f}s on their own; cost ${cost:.3f}", file=out)
    return 0


def main(argv: Sequence[str], **kwargs) -> int:
    parser = argparse.ArgumentParser(prog="measure_review.py", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "score"):
        sub = commands.add_parser(name)
        sub.add_argument("--run", type=Path, required=True, help="a corpus run that kept its answers")
        sub.add_argument("--pass", dest="number", type=int, required=True)
        sub.add_argument("--root", type=Path, default=Path("."))
        sub.add_argument("--corpus", type=Path, default=REPO / "corpus" / "annotations.jsonl")
        sub.add_argument("out", type=Path, help="JSONL file the reviews are appended to")
        if name == "run":
            sub.add_argument("--config", type=Path)
            sub.add_argument("--prompt", type=Path)
            sub.add_argument("--only", type=Path, help="a file naming the reports to review")
            sub.add_argument("--limit", type=int)
            sub.add_argument("--deadline", type=float, default=DEADLINE_S)
    args = parser.parse_args(list(argv)[1:])
    if args.command == "run":
        return run(args, **kwargs)
    return score(args, **{k: v for k, v in kwargs.items() if k == "out"})


if __name__ == "__main__":
    sys.exit(main(sys.argv))

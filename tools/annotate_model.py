#!/usr/bin/env python3
"""Annotate captured reports with a model, the reference A-12 allows since 23 October 2026.

    python3 tools/annotate_model.py [--model MODEL] [--only REPORT]... [--limit N]
                                    [--corpus PATH] [--dry-run] PROJECT [PROJECT ...]

Each report still to do goes to the model as the extractor gets it, cut by
ledger.sentences into numbered sentences, after the rules of
docs/ANNOTATING.md, and with nothing else: not the turn's evidence, not the
extractor's answer. The model says which sentences claim something and of what
type, with a span copied out of the sentence where one sentence holds more
than one claim. The answer is checked as tools/annotate.py checks a person's,
and appended to the corpus in the same shape, signed with the model that gave
it and the CLI that carried it.

The model is reached through the Claude Code CLI in print mode, on the account
the CLI is logged into, so that a subscription pays for it. It runs with no
tools, no MCP servers, no slash commands and no saved session, from an empty
folder outside every project and with project settings only, of which an empty
folder has none: no CLAUDE.md, memory, plugin or hook of a project or of the
user reaches it, and the claim-ledger hooks a project installs do not capture
its answer as a report. Its environment is this one without the variables a
Claude Code session sets for its children, so that it runs as from a terminal,
not inside the session that may have started this tool.

An answer that does not parse, names a sentence the report does not have, a
type outside the vocabulary, or a span that is not in its sentence word for
word, leaves the report unannotated and named; nothing is repaired. So does an
answer the CLI reports as an error, or one a model other than MODEL gave. A
report longer than its project's [extractor] max_report_chars is left out,
since the extractor never reads it. --dry-run prints what the first report
still to do would send, and calls nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TextIO

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

import annotate  # noqa: E402
from ledger import config, schema, sentences  # noqa: E402

MODEL = "claude-fable-5-1"
GUIDE = REPO / "docs" / "ANNOTATING.md"
TIMEOUT_S = 600.0
#: What a Claude Code session sets for the processes it starts. The CLI started
#: with them runs as that session's child, not as from a terminal.
SESSION_PREFIXES = ("CLAUDE_CODE_", "CLAUDECODE", "ANTHROPIC_")
_FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\Z", re.DOTALL)

INSTRUCTIONS = """\
You are annotating one report for a measurement corpus. The report is the
message an AI coding agent wrote to its user at the end of a turn. Say which of
its sentences claim something, and of which type, by the rules of the
annotation guide below, applied exactly as a person annotating by hand would
apply them. Mark what the report says, not what you think happened.

The guide was written for a person using a tool that asks about one sentence
at a time; you answer for all of them at once. Its keys 1 to 5 are the types
{types}. Where the guide says to split a sentence with `s`, give each of its
claims with its own span.

Answer with one JSON object and nothing else:
{{"claims": [{{"sentence": <number>, "type": "<type>"}}, ...]}}
- One item per claim; leave out the sentences that claim nothing.
- "type" is one of {types}.
- Add "span" only when a sentence holds more than one claim, or a claim is only
  part of its sentence: the words of that claim, copied from that sentence
  character for character.

<guide>
{guide}
</guide>

<report>
{report}
</report>
"""


class AnnotationError(Exception):
    """This report's answer cannot be trusted as given, and it stays unannotated."""


def prompt_for(cut: Sequence[str], guide: str) -> str:
    """What the model is sent: the guide, the report's numbered sentences, and nothing else."""
    return INSTRUCTIONS.format(types=", ".join(schema.CLAIM_TYPES), guide=guide.strip(),
                               report=sentences.numbered(cut))


def cli_command(model: str) -> list[str]:
    """The CLI in print mode, answering in JSON, with nothing to reach but the prompt."""
    return ["claude", "-p", "--model", model, "--output-format", "json",
            "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
            "--no-session-persistence", "--setting-sources", "project"]


def cli_env(environ: Mapping[str, str]) -> dict[str, str]:
    """This environment without what a Claude Code session sets for its children."""
    return {name: value for name, value in environ.items()
            if not name.startswith(SESSION_PREFIXES)}


def run_cli(prompt: str, *, model: str, timeout_s: float = TIMEOUT_S) -> dict:
    """One answer, from an empty folder outside every project; the CLI's JSON envelope."""
    with tempfile.TemporaryDirectory(prefix="annotate-model-") as empty:
        try:
            done = subprocess.run(cli_command(model), input=prompt, capture_output=True,
                                  text=True, cwd=empty, env=cli_env(os.environ),
                                  timeout=timeout_s)
        except subprocess.TimeoutExpired as e:
            raise AnnotationError(f"no answer within {timeout_s:g}s") from e
        except OSError as e:
            raise AnnotationError(f"the CLI did not start: {e}") from e
    if done.returncode != 0:
        raise AnnotationError(f"the CLI exited {done.returncode}: "
                              f"{(done.stderr or done.stdout).strip()[:300]}")
    try:
        envelope = json.loads(done.stdout)
    except ValueError as e:
        raise AnnotationError(f"the CLI's output is not JSON: {done.stdout[:200]!r}") from e
    if not isinstance(envelope, dict):
        raise AnnotationError("the CLI's output is not a JSON object")
    return envelope


def cli_version() -> str:
    done = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                          env=cli_env(os.environ), timeout=60)
    return done.stdout.strip().split(" ")[0] or "unknown"


def parse(envelope: Mapping, cut: Sequence[str], *, model: str) -> tuple[list[dict], str]:
    """The claims of one answer, checked against the report's sentences, and who gave it."""
    if envelope.get("is_error") or envelope.get("subtype", "success") != "success":
        raise AnnotationError(f"the CLI reports an error: {str(envelope.get('result'))[:200]}")
    answered_by = _answered_by(envelope, model)
    text = envelope.get("result")
    if not isinstance(text, str):
        raise AnnotationError("the CLI's output carries no answer")
    answer = _json_object(text)
    listed = answer.get("claims") if isinstance(answer, dict) else None
    if not isinstance(listed, list) or set(answer) != {"claims"}:
        raise AnnotationError("the answer is not one object holding a claims list")
    claims: list[dict] = []
    for position, item in enumerate(listed, 1):
        claim = _claim(item, cut, f"claims[{position}]")
        if claim not in claims:
            claims.append(claim)
    return claims, answered_by


def _claim(item: object, cut: Sequence[str], where: str) -> dict:
    if not isinstance(item, dict) or not {"sentence", "type"} <= set(item) <= {
            "sentence", "type", "span"}:
        raise AnnotationError(f"{where} is not a sentence, a type and maybe a span")
    number = item["sentence"]
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(cut):
        raise AnnotationError(f"{where} names sentence {number!r}, and the report has "
                              f"{len(cut)}")
    if item["type"] not in schema.CLAIM_TYPES:
        raise AnnotationError(f"{where}.type is {item['type']!r}, not one of "
                              f"{list(schema.CLAIM_TYPES)}")
    sentence = cut[number - 1]
    span = item.get("span", sentence)
    if not isinstance(span, str) or not span.strip() or span.strip() not in sentence:
        raise AnnotationError(f"{where}.span is not in sentence {number} word for word")
    return {"span": span.strip(), "type": item["type"]}


def _answered_by(envelope: Mapping, model: str) -> str:
    """The model that wrote the answer: the one with the most output, which must be MODEL."""
    usage = envelope.get("modelUsage")
    if not isinstance(usage, dict) or not usage:
        raise AnnotationError("the CLI's output does not say which model answered")
    main = max(usage, key=lambda name: (usage[name] or {}).get("outputTokens", 0))
    if model not in main:
        raise AnnotationError(f"answered by {main}, not {model}")
    return main


def _json_object(text: str) -> object:
    stripped = text.strip()
    fenced = _FENCE.match(stripped)
    try:
        return json.loads(fenced.group(1) if fenced else stripped)
    except ValueError as e:
        raise AnnotationError(f"the answer is not JSON: {e}") from e


def _too_long(report: annotate.Report, projects: Sequence[Path],
              limits: Mapping[Path, int]) -> bool:
    for project in projects:
        if report.path.is_relative_to(project):
            return len(report.text) > limits[project]
    return False


def main(argv: list[str], *, run: Callable[..., dict] = run_cli,
         version: Callable[[], str] = cli_version, today: Callable[[], date] = date.today,
         out: TextIO | None = None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path,
                        help="project roots whose captured reports to annotate")
    parser.add_argument("--model", default=MODEL,
                        help=f"the model that annotates (default {MODEL})")
    parser.add_argument("--only", action="append", metavar="REPORT",
                        help="annotate only this report, by id; give it once per report")
    parser.add_argument("--limit", type=int, help="stop after this many reports")
    parser.add_argument("--corpus", type=Path, default=annotate.CORPUS,
                        help="the file annotations are appended to "
                             "(default: corpus/annotations.jsonl in this repository)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what the first report still to do would send, "
                             "and call nothing")
    args = parser.parse_args(argv[1:])
    projects = [project.resolve() for project in args.projects]

    try:
        done = annotate.annotated(args.corpus)
        reports, unreadable = annotate.find_reports(projects)
        limits = {project: config.load(project / config.CONFIG_FILENAME)
                  .extractor.max_report_chars for project in projects}
    except (annotate.AnnotateError, config.ConfigError) as e:
        print(e, file=sys.stderr)
        return 2
    for problem in unreadable:
        print(f"left out, it does not read as a captured report: {problem}", file=sys.stderr)

    pending = [report for report in reports if report.report_id not in done]
    if args.only:
        wanted = set(args.only)
        for missing in sorted(wanted - {report.report_id for report in pending}):
            print(f"{missing} is not a report still to do", file=sys.stderr)
        pending = [report for report in pending if report.report_id in wanted]
    for report in [r for r in pending if _too_long(r, projects, limits)]:
        print(f"left out, longer than the extractor reads: {report.report_id} "
              f"({len(report.text)} characters)", file=sys.stderr)
    pending = [r for r in pending if not _too_long(r, projects, limits)]
    if args.limit is not None:
        pending = pending[:args.limit]
    print(f"{len(done)} annotated in {args.corpus}; {len(pending)} to send to {args.model}",
          file=out)

    guide = GUIDE.read_text(encoding="utf-8")
    if args.dry_run:
        if pending:
            print(prompt_for(sentences.split(pending[0].text), guide), file=out)
        return 0
    carried_by = f"Claude Code {version()}" if pending else ""
    saved = failed = 0
    for report in pending:
        cut = sentences.split(report.text)
        try:
            if cut:
                claims, answered_by = parse(run(prompt_for(cut, guide), model=args.model),
                                            cut, model=args.model)
            else:                                  # nothing to ask, as by hand
                claims, answered_by = [], args.model
        except AnnotationError as e:
            print(f"left {report.report_id} unannotated: {e}", file=sys.stderr)
            failed += 1
            continue
        try:
            annotate.append(args.corpus, {"report": report.report_id,
                                          "annotated": today().isoformat(),
                                          "by": f"{answered_by} via {carried_by}",
                                          "claims": claims})
        except (annotate.AnnotateError, OSError) as e:
            print(e, file=sys.stderr)
            return 2
        saved += 1
        print(f"saved {report.report_id}: {len(claims)} claims in {len(cut)} sentences",
              file=out, flush=True)               # a long run shows its progress
    print(f"{saved} saved, {failed} left unannotated", file=out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

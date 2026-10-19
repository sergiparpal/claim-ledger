#!/usr/bin/env python3
"""What daily use of the ledger has recorded, read back for the questions it raised.

    python3 tools/daily_use.py recording [--root PROJECT] [--transcripts DIR] [SESSION ...]
    python3 tools/daily_use.py latency [--root PROJECT] [--transcripts DIR]
    python3 tools/daily_use.py verdicts [--root PROJECT] [--spans]
    python3 tools/daily_use.py defects [--root PROJECT] [--spans]
    python3 tools/daily_use.py referents [--root PROJECT]

`recording` sets every tool call in a session's Claude Code transcript beside
the session's evidence log. A call the recorder's matcher covers that left no
record, or a record no call accounts for, is a hole in the log, and every
verdict above a hole is uninterpretable: this is the phase-0 check of SPEC §
Build order, made for any session. With no SESSION it checks every session
found in both places, and it exits 1 when it finds a hole.

`latency` pairs every Stop the hook ran with the report it captured: how long
the hook took, from the `durationMs` Claude Code writes into the transcript
(the only record of it), and how the turn ended. An empty answer writes nothing
to claims.jsonl and no line to errors.log, and is told from a hook that never
ran only by the appendix in the transcript, `0 verified, 0 unchecked`. The
`x fast` column is a rough guess at how slow the route was: the hook's time
against what the fast run of 17 October 2026 would have taken over the claims
kept, read at 3.2 characters a token.

`verdicts` lists the `VERIFIED` claims a person should read, of the two kinds
docs/DECISIONS.md records: a claim verified on one of several referents while
another reaches nothing, and a claim with a negative word in it, which may be
verified by the write it denies. Both are candidates, not findings, and the
negative words are a short list in Spanish and English.

`defects` shows how each span the extractor returned and the report does not
contain differs from the nearest text in the report. Since the sentence
contract of 18 October 2026 the model returns numbers, not text, and a defect
is a number naming no sentence; those are listed as such.

`referents` counts, for each route in claims.jsonl, the checkable claims whose
referents the join could match at all (`usable` in tools/measure_route.py),
judged against PROJECT's configuration as it is now, and how many of the
UNSUPPORTED ones could match nothing. Such a claim stays UNSUPPORTED whatever
the log holds, and recall, matched by sentence and type, does not see it.

Transcripts are read from where Claude Code keeps them for PROJECT, or from
--transcripts. Nothing is written anywhere.

`verdicts` and `defects` print the extractor's spans only with --spans:
without it, `verdicts` shows claim ids, referents and the record that decided,
and `defects` only the text that changed. A report read beside the extractor's
list is annotated against it (docs/ANNOTATING.md), so ask for the spans on
reports already annotated, or knowingly.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

from ledger import config, evidence, join, turn  # noqa: E402
import measure_route  # noqa: E402  the fast run, the yardstick for "x fast"

CHARS_PER_TOKEN = 3.2      # characters of answer per output token, 17 October 2026
HOOK_OVERHEAD_S = 0.1      # the pipeline around the call, as the too-long turns took
NEGATIVE = re.compile(r"(?<!\w)(no|ni|sin|nada|nunca|not|never|nothing|none|without)(?!\w)"
                      r"|n't", re.IGNORECASE)
SIZES = ((0, 3000), (3000, 6000), (6000, 10000), (10000, 1_000_000))


def recording(args) -> int:
    """Every call beside its record. Three kinds of unrecorded call are not holes:
    one recorded under the session this one resumed, whose history its transcript
    carries over; one the harness refused or blocked, which fires no hook (R-44);
    and one cancelled before a result came back. A failed call does fire one, so
    an error with no record is shown with its first line, which tells the two
    apart. A call that ran with no record anywhere, and a record no call
    accounts for, are holes."""
    covered = set(json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
                  ["hooks"]["PostToolUse"][0]["matcher"].split("|"))
    folder = _transcripts(args)
    logs = sorted((args.root / evidence.STATE_DIR / "sessions").glob("*.jsonl"))
    records, unreadable = {}, {}
    for log in logs:
        try:
            records[log.stem] = {e.record.get("tool_use_id") for e in evidence.read(log)}
        except evidence.EvidenceError as e:
            unreadable[log.stem] = str(e)
    anywhere = set().union(*records.values()) if records else set()
    sessions = args.sessions or sorted(log.stem for log in logs if (folder / log.name).exists())
    holes = 0
    for session in sessions:
        if session in unreadable:
            print(f"{session[:8]}  the log cannot be read: {unreadable[session]}")
            holes += 1
            continue
        if not (folder / f"{session}.jsonl").exists():
            print(f"{session[:8]}  no transcript in {folder}: not checked")
            continue
        # A subagent's calls are recorded too, and its transcript sits beside the session's.
        calls = [call for path in [folder / f"{session}.jsonl",
                                   *sorted((folder / session).rglob("*.jsonl"))]
                 for call in _tool_calls(path)]
        here = records.get(session, set())
        mine = [c for c in calls if c["name"] in covered]
        unrecorded = [c for c in mine if c["id"] not in here]
        carried = [c for c in unrecorded if c["id"] in anywhere]
        ran = [c for c in unrecorded if c["id"] not in anywhere and c["result"] == "ran"]
        erred = [c for c in unrecorded if c["id"] not in anywhere and c["result"] == "error"]
        cancelled = [c for c in unrecorded if c["id"] not in anywhere
                     and c["result"] == "no result"]
        stray = sorted(here - {c["id"] for c in calls})
        tools = ", ".join(f"{name} {n}" for name, n in Counter(c["name"] for c in calls).items())
        print(f"{session[:8]}  {len(calls)} calls ({tools or 'none'}); of the {len(mine)} the "
              f"recorder covers, {len(mine) - len(unrecorded)} recorded here, {len(carried)} "
              f"under an earlier session, {len(erred)} errors and {len(cancelled)} cancelled "
              f"with no record, {len(ran)} ran with no record; "
              f"{len(stray)} records with no call")
        for call in ran:
            print(f"    ran, no record:  {call['name']} {call['id']} {call['summary'][:70]}")
        for call in erred:
            print(f"    error, no record: {call['name']} {call['id']}: {call['error']}")
        for tool_use_id in stray:
            print(f"    record, no call: {tool_use_id}")
        holes += len(ran) + len(stray)
    print(f"\n{len(sessions)} sessions, {holes} holes")
    return 1 if holes else 0


def latency(args) -> int:
    runs = _stop_runs(_transcripts(args))
    errors = _errors(args.root)
    kept = _kept(args.root)
    headers = []
    for path in sorted((args.root / evidence.STATE_DIR / turn.REPORTS).glob("*.md")):
        try:
            headers.append(turn.read_capture(path)[0])
        except turn.TurnError as e:
            print(f"skipped: {e}")
    captures = defaultdict(list)
    for header in headers:
        captures[header["session"]].append(header["captured"])
    turns = []
    for header in headers:
        session, number = header["session"], int(header["turn_number"])
        captured, chars = header["captured"], int(header["report_chars"])
        # The hook's run for this turn ends after its capture and before the next one's.
        later = [c for c in captures[session] if c > captured]
        until = min(later) if later else "~"
        run = next((r for r in runs.get(session, []) if captured <= r[0] < until), None)
        what = kept.get((session, number))
        turns.append({"captured": captured, "session": session, "turn": number,
                      "chars": chars, "seconds": run[1] / 1000 if run else None,
                      "ended": ending(errors.get((session, number)), what, run),
                      "claims": what["claims"] if what else 0,
                      "defects": what["defects"] if what else 0,
                      "kept_chars": what["chars"] if what else 0})
    print(f"{'captured UTC':16}  {'session':8} {'n':>2} {'chars':>6} {'hook s':>6}  "
          f"{'ended':14} {'claims':>6} {'defects':>7} {'x fast':>6}")
    for t in sorted(turns, key=lambda t: t["captured"]):
        print(f"{t['captured'][:16]:16}  {t['session'][:8]} {t['turn']:>2} {t['chars']:>6} "
              f"{_seconds(t['seconds']):>6}  {t['ended']:14} {t['claims']:>6} "
              f"{t['defects']:>7} {_times_fast(t):>6}")
    print("\nended: " + ", ".join(f"{k} {n}" for k, n in Counter(t["ended"] for t in turns)
                                   .most_common()))
    reached = [t for t in turns if t["ended"] in ("answered", "empty answer", "deadline")]
    print(f"of the {len(reached)} turns whose call answered or ran out of time, "
          f"{sum(1 for t in reached if t['ended'] == 'deadline')} passed the deadline and "
          f"{sum(1 for t in reached if t['ended'] == 'empty answer')} came back empty")
    days = defaultdict(list)
    for t in reached:
        days[t["captured"][:10]].append(t)
    for day, those in sorted(days.items()):
        answered = [t["seconds"] for t in those if t["ended"] == "answered" and t["seconds"]]
        print(f"  {day}: {len(those):>2} turns, "
              f"{sum(1 for t in those if t['ended'] == 'deadline'):>2} past the deadline, "
              f"{sum(1 for t in those if t['ended'] == 'empty answer')} empty; answered in "
              + (f"{statistics.median(answered):.1f}s median" if answered else "-"))
    for low, high in SIZES:
        those = [t for t in reached if low <= t["chars"] < high]
        sized = f"{low}-{high - 1}" if high < SIZES[-1][1] else f"{low} or more"
        print(f"  reports of {sized:>11} characters: {len(those):>2} turns, "
              f"{sum(1 for t in those if t['ended'] == 'deadline'):>2} past the deadline")
    return 0


def ending(error: str | None, kept: Mapping | None, run: tuple | None) -> str:
    """How a turn's extraction ended, from what the ledger and the transcript hold."""
    if error:
        code = re.search(r"HTTP (\d{3})", error)
        if "deadline" in error:
            return "deadline"
        if code:
            return f"http {code.group(1)}"
        if "characters, over the" in error:
            return "too long"
        return "unknown"
    if kept:
        return "answered"
    if run is None:
        return "no hook found"
    if "0 verified, 0 unchecked" in run[2] and "EXTRACTION DEFECTS" not in run[2]:
        return "empty answer"
    return "unclear"


def verdicts(args) -> int:
    rows = [row for row in _claim_rows(args.root) if row.get("row") == "claim"
            and row.get("verdict") == "VERIFIED"]
    logs: dict[str, list] = {}
    partial = []
    for row in rows:
        if row["type"] not in ("command_run", "file_changed") or len(row["referents"]) < 2:
            continue
        if row["session"] not in logs:
            try:
                logs[row["session"]] = evidence.read(
                    evidence.session_log(args.root, row["session"]))
            except evidence.EvidenceError as e:
                print(f"  skipped: {e}")
                logs[row["session"]] = []
        before = [e for e in logs[row["session"]] if e.position <= row["position"]]
        if not before or before[-1].position != row["position"]:
            continue                       # the log no longer holds what decided it
        names = join.names_command if row["type"] == "command_run" else join.names_path
        unreached = [r for r in row["referents"] if not names([r], before[-1].record)]
        if unreached:
            nowhere = [r for r in unreached if not any(names([r], e.record) for e in before)]
            partial.append((row, unreached, nowhere))
    print(f"VERIFIED on one referent while another does not reach the record that "
          f"verified it: {len(partial)}")
    for row, unreached, nowhere in partial:
        print(f"  {row['claim_id']}  {row['type']}  referents {row['referents']}; not "
              f"reached {unreached}" + (f", of them reaching nothing at all {nowhere}"
                                        if nowhere else ""))
        _show(row, args.spans)
    negated = [row for row in rows if NEGATIVE.search(row["span"])]
    print(f"\nVERIFIED with a negative word in the span: {len(negated)}")
    for row in negated:
        print(f"  {row['claim_id']}  {row['type']}  referents {row['referents']}")
        _show(row, args.spans)
    return 0


def referents(args) -> int:
    cfg = config.load(args.root / config.CONFIG_FILENAME)
    commands = measure_route.recorded_commands(args.root)
    routes = defaultdict(list)
    for row in _claim_rows(args.root):
        if row.get("row") == "claim" and row.get("type") in measure_route.CHECKABLE:
            route = row.get("route") or {}
            routes[(route.get("model", "?"), route.get("prompt_version", "?"))].append(row)
    print(f"checkable claims whose referents the join could match, against "
          f"{config.CONFIG_FILENAME} as it is now")
    for (model, prompt), rows in sorted(routes.items()):
        matches = [measure_route.usable(row["type"], row.get("referents") or [], cfg,
                                        args.root, commands) for row in rows]
        turns = {(row["session"], row["turn_number"]) for row in rows}
        cells = [f"{kind} {sum(m for row, m in zip(rows, matches) if row['type'] == kind)} of "
                 f"{sum(1 for row in rows if row['type'] == kind)}"
                 for kind in measure_route.CHECKABLE]
        unsupported = [m for row, m in zip(rows, matches) if row.get("verdict") == "UNSUPPORTED"]
        print(f"  {model}, {prompt}, {len(turns)} turn{'s' if len(turns) != 1 else ''}: "
              f"{sum(matches)} of {len(rows)} "
              f"({sum(matches) / len(rows):.0%}); {', '.join(cells)}; of {len(unsupported)} "
              f"UNSUPPORTED, {unsupported.count(False)} could match nothing")
    return 0


def defects(args) -> int:
    rows = [row for row in _claim_rows(args.root) if row.get("row") == "defect"]
    kinds = Counter()
    for row in rows:
        path = (args.root / evidence.STATE_DIR / turn.REPORTS
                / f"{row['session']}-{row['turn_number']}.md")
        if row.get("reason", "").startswith("the report has"):
            # Under the sentence contract a defect is a number naming no sentence:
            # there is no copied text to set beside the report.
            kinds["no such sentence"] += 1
            print(f"  {row['claim_id']}: {row['span']}, but {row['reason']}")
            continue
        try:
            _, report = turn.read_capture(path)
        except (OSError, turn.TurnError):
            print(f"  {row['claim_id']}: its report is not captured")
            continue
        changes, window = differences(row["span"], report)
        kinds.update(kind for kind, _ in changes)
        print(f"  {row['claim_id']}: " + "; ".join(text for _, text in changes))
        if args.spans:
            print(f"      span:   {row['span']!r}\n      report: {window!r}")
    print(f"\n{len(rows)} defects; differences by kind: "
          + (", ".join(f"{k} {n}" for k, n in kinds.most_common()) or "none"))
    return 0


def differences(span: str, report: str) -> tuple[list[tuple[str, str]], str]:
    """How a span differs from the stretch of the report it was taken from.

    The stretch is placed by the longest run the two share, widened to the
    span's length, so the differences at its edges are the span's, not the
    window's.
    """
    anchor = difflib.SequenceMatcher(None, report, span, autojunk=False).find_longest_match(
        0, len(report), 0, len(span))
    if not anchor.size:
        return [("other", "nothing in common with the report")], ""
    start = max(0, anchor.a - anchor.b - 5)
    window = report[start:min(len(report), anchor.a + len(span) - anchor.b + 5)]
    codes = difflib.SequenceMatcher(None, window, span, autojunk=False).get_opcodes()
    while codes and codes[0][0] == "delete":
        codes = codes[1:]                  # the slack before the span, not a change
    while codes and codes[-1][0] == "delete":
        codes = codes[:-1]                 # and after it
    changes = []
    for group in _within_words(codes, window):
        i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]
        changed = "".join(window[a:b] + span[c:d] for _, a, b, c, d in group)
        if any(ch.isalnum() for ch in changed):
            # A changed word reads as a word: widen to it on both sides.
            while i1 and j1 and window[i1 - 1].isalnum() and window[i1 - 1] == span[j1 - 1]:
                i1, j1 = i1 - 1, j1 - 1
            while (i2 < len(window) and j2 < len(span) and window[i2].isalnum()
                   and window[i2] == span[j2]):
                i2, j2 = i2 + 1, j2 + 1
        before, after = window[i1:i2], span[j1:j2]
        if not after:
            changes.append((_kind(changed), f"dropped {before!r}"))
        elif not before:
            changes.append((_kind(changed), f"added {after!r}"))
        else:
            changes.append((_kind(changed), f"{before!r} became {after!r}"))
    if codes:
        window = window[codes[0][1]:codes[-1][2]]
    return changes or [("other", "no difference found")], window


def _within_words(codes: Sequence[tuple], window: str) -> list[list[tuple]]:
    """The changes, with those inside one word joined: a run of up to three
    letters between two changes is the same word changing, not two edits."""
    groups, current = [], []
    for position, code in enumerate(codes):
        tag, i1, i2 = code[0], code[1], code[2]
        if tag != "equal":
            current.append(code)
            continue
        inside = (current and i2 - i1 <= 3 and window[i1:i2].isalnum()
                  and position + 1 < len(codes))
        if current and not inside:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _kind(text: str) -> str:
    if all(c in "*_`#~" for c in text):
        return "markup"
    if all(c in "«»“”\"'‘’" for c in text):
        return "quotes"
    if all(c in ".,;:!?…" for c in text):
        return "punctuation"
    if text.isspace():
        return "spacing"
    return "words"


def _show(row: Mapping, spans: bool) -> None:
    print(f"      {row.get('scope')}")
    if spans:
        print(f"      {row['span']!r}")


def _tool_calls(path: Path) -> list[dict]:
    calls, results = [], {}
    for line in _lines(path):
        message = line.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if line.get("type") == "assistant" and block.get("type") == "tool_use":
                given = block.get("input") or {}
                summary = (given.get("command") or given.get("file_path")
                           or given.get("notebook_path") or "")
                calls.append({"id": block.get("id"), "name": block.get("name"),
                              "summary": str(summary).split("\n")[0]})
            elif line.get("type") == "user" and block.get("type") == "tool_result":
                said = block.get("content")
                if isinstance(said, list):
                    said = " ".join(b.get("text", "") for b in said if isinstance(b, dict))
                results[block.get("tool_use_id")] = (
                    "error" if block.get("is_error") else "ok",
                    str(said or "").strip().split("\n")[0][:100])
    for call in calls:
        result, first_line = results.get(call["id"], (None, ""))
        call["result"] = {"ok": "ran", "error": "error"}.get(result, "no result")
        call["error"] = first_line if result == "error" else ""
    return calls


def _stop_runs(folder: Path) -> dict[str, list[tuple[str, int, str]]]:
    """Every Stop the ledger's hook ran, by session: when, how long, what it printed."""
    runs = defaultdict(list)
    for path in sorted(folder.glob("*.jsonl")):
        for line in _lines(path):
            attached = line.get("attachment") or {}
            if (line.get("type") != "attachment" or attached.get("type") != "hook_success"
                    or attached.get("hookEvent") != "Stop"
                    or "claim-ledger" not in (attached.get("stdout") or "")):
                continue
            try:
                message = json.loads(attached["stdout"]).get("systemMessage", "")
            except ValueError:
                message = attached["stdout"]
            runs[line.get("sessionId") or path.stem].append(
                (line.get("timestamp", ""), attached.get("durationMs") or 0, message))
    return {session: sorted(found) for session, found in runs.items()}


def _errors(root: Path) -> dict[tuple[str, int], str]:
    found = {}
    for line in _lines(root / evidence.STATE_DIR / "errors.log"):
        if line.get("component") == "turn":
            found[(line.get("session"), line.get("turn_number"))] = line.get("error", "")
    return found


def _kept(root: Path) -> dict[tuple[str, int], dict]:
    """What claims.jsonl holds for each turn: claims, defects, and their size."""
    found = defaultdict(lambda: {"claims": 0, "defects": 0, "chars": 0})
    for row in _claim_rows(root):
        what = found[(row.get("session"), row.get("turn_number"))]
        if row.get("row") == "claim":
            what["claims"] += 1
            answer = {k: row.get(k) for k in ("span", "type", "referents")}
            what["chars"] += len(json.dumps(answer, ensure_ascii=False)) + 2
        elif row.get("row") == "defect":
            what["defects"] += 1
    return dict(found)


def _times_fast(t: Mapping) -> str:
    if t["ended"] != "answered" or not t["seconds"] or not t["kept_chars"]:
        return "-"
    tokens = t["kept_chars"] / CHARS_PER_TOKEN
    expected = HOOK_OVERHEAD_S + measure_route.FAST_S + measure_route.FAST_PER_TOKEN_S * tokens
    return f"{t['seconds'] / expected:.1f}"


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _claim_rows(root: Path) -> list[dict]:
    return list(_lines(root / evidence.STATE_DIR / "claims.jsonl"))


def _lines(path: Path) -> Iterable[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    found = []
    # Split on newlines only: splitlines() also breaks at U+2028 and its kin, which
    # a JSON string may carry raw, and the record it cut in two would be lost.
    for line in text.split("\n"):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue                       # a transcript line being written as we read
        if isinstance(parsed, dict):
            found.append(parsed)
    return found


def _transcripts(args) -> Path:
    """Where Claude Code keeps PROJECT's transcripts, unless --transcripts says."""
    if args.transcripts:
        return args.transcripts
    named = re.sub(r"[^A-Za-z0-9]", "-", str(args.root.resolve()))
    return Path.home() / ".claude" / "projects" / named


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Read back what daily use has recorded.")
    commands = parser.add_subparsers(dest="command", required=True)

    def common(sub, *, transcripts: bool = False, spans: bool = False):
        sub.add_argument("--root", type=Path, default=Path("."),
                         help="project whose .claude/claim-ledger/ is read")
        if transcripts:
            sub.add_argument("--transcripts", type=Path,
                             help="folder of the project's Claude Code transcripts")
        if spans:
            sub.add_argument("--spans", action="store_true",
                             help="print the extractor's spans as well")

    seen = commands.add_parser("recording", help="every tool call beside its record")
    common(seen, transcripts=True)
    seen.add_argument("sessions", nargs="*", help="sessions to check (default: all)")
    common(commands.add_parser("latency", help="how long each Stop took, how it ended"),
           transcripts=True)
    common(commands.add_parser("verdicts", help="VERIFIED claims a person should read"),
           spans=True)
    common(commands.add_parser("defects", help="how dropped spans differ from the report"),
           spans=True)
    common(commands.add_parser("referents", help="claims naming what the join can match"))

    args = parser.parse_args(list(argv[1:]))
    try:
        return {"recording": recording, "latency": latency, "verdicts": verdicts,
                "defects": defects, "referents": referents}[args.command](args)
    except (OSError, config.ConfigError, evidence.EvidenceError, turn.TurnError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

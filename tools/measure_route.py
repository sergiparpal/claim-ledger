#!/usr/bin/env python3
"""Measure the extraction route: how long it takes, and whether it answers alike.

    python3 tools/measure_route.py run [--root PROJECT] [--passes N] [--deadline S]
                                       [--same-reports RUN.jsonl] OUT.jsonl
    python3 tools/measure_route.py watch --probe REPORT [--root PROJECT] [--every S]
                                         [--slow X] [--hours H] OUTDIR
    python3 tools/measure_route.py summary [--root PROJECT] RUN.jsonl [RUN.jsonl ...]
    python3 tools/measure_route.py fixture [--root PROJECT] [--runs N]

`run` sends the request the Stop hook sends, built by the same code from
PROJECT/claim-ledger.toml, for every report PROJECT has captured under
`max_report_chars`: each one --passes times (default 2), every pass in its own
shuffled order, with the fixed report of docs/provider-measurements.md every
tenth call. One call at a time, a second apart, as turns come. The deadline is
a wall clock of --deadline seconds (default 150) rather than the route's own,
because a call abandoned at the deadline says nothing about how long it would
have taken; the client's single retry stays, as in the hook. --same-reports
takes the reports of an earlier run instead of what PROJECT holds now, so that
two runs compare report for report and, with the same --seed, call for call.
The default seed is the one the runs of 17 October 2026 used.

`watch` sends one --probe report every --every seconds (default 300) and starts
`run` when the route turns slow: two probes in a row at --slow times (default
2) what the fast run of 17 October 2026 predicts for their answer, or one past
the route's own deadline. A new deadline entry in PROJECT's errors.log brings
the next probe forward. It stops after the run, or after --hours (default 24)
without one, writing probes.jsonl and run.jsonl into OUTDIR.

`summary` prints what docs/provider-measurements.md reports for a run: the
tail, the share inside each deadline, the time per output token, where the
time went, and how far the answers agree, within a run and across runs. With
--root it also times the reports whose turns passed the deadline in the hook.

`fixture` asks about the fixed report --runs times (default 3) and prints each
answer beside the one recorded on 23 September 2026.

Each call is timed in stages, DNS, TCP, TLS, first byte and whole body, by a
POST made as urllib makes it, since urllib times none of them. The key comes
from the variable `[extractor] key_env` names, as for the hook; see
docs/OPERATING.md for where it lives.

Nothing kept or printed names a claim of a captured report: the corpus is
annotated by hand, and an annotator who has seen the extractor's list confirms
it. A run keeps timings, sizes, a digest of each answer, and counts. `fixture`
prints claims because its report is a test fixture, not part of the corpus.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import http.client
import json
import os
import random
import socket
import ssl
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO)]

from ledger import budget, config, evidence, extract, schema, turn  # noqa: E402
from tests.test_extract import CAPTURED_REPORT  # noqa: E402  the fixed report

FIXED = "fixed-442"
RECORDING = REPO / "tests" / "fixtures" / "extractor" / "openrouter-deepseek-v4.1-flash.json"
SEED = 20261017
FIXED_EVERY = 10
PAUSE_S = 1.0
# The fast run of 17 October 2026 (docs/provider-measurements.md): an answer of
# n output tokens took about FAST_S + FAST_PER_TOKEN_S * n seconds.
FAST_S, FAST_PER_TOKEN_S = 0.65, 0.0047
LIMITS = (12, 15, 20, 25, 30, 45, 60, 90)

#: What `call` hands its POST, and what it gets back: status, body, stages.
Post = Callable[[extract.Request, float], tuple[int, bytes, dict]]


def staged_post(request: extract.Request, timeout_s: float) -> tuple[int, bytes, dict]:
    """The POST extract.https_transport makes, with each stage of it timed."""
    key = os.environ.get(request.key_env)
    if not key:
        raise extract.ExtractError(f"{request.key_env} is not set")
    url = urlsplit(request.url)
    host, port = url.hostname, url.port or 443
    headers = {"content-type": "application/json", "anthropic-version": extract.API_VERSION,
               "Connection": "close",
               "User-Agent": f"Python-urllib/{sys.version_info[0]}.{sys.version_info[1]}"}
    headers["x-api-key" if request.auth == "x-api-key" else "authorization"] = (
        key if request.auth == "x-api-key" else f"Bearer {key}")
    stages = {}
    try:
        mark = time.monotonic()
        address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][4][:2]
        stages["dns"], mark = time.monotonic() - mark, time.monotonic()
        raw = socket.create_connection(address, timeout=timeout_s)
        stages["tcp"], mark = time.monotonic() - mark, time.monotonic()
        context = ssl.create_default_context()
        context.set_alpn_protocols(["http/1.1"])
        connection = http.client.HTTPSConnection(host, port, timeout=timeout_s)
        connection.sock = context.wrap_socket(raw, server_hostname=host)
        stages["tls"], mark = time.monotonic() - mark, time.monotonic()
        connection.request("POST", url.path, body=json.dumps(request.body).encode("utf-8"),
                           headers=headers)
        reply = connection.getresponse()
        stages["first_byte"] = time.monotonic() - mark
        body = reply.read()
        stages["api"] = time.monotonic() - mark
        connection.close()
    except (OSError, http.client.HTTPException) as e:
        raise extract.ExtractError(f"the model call did not complete: {e}") from e
    return reply.status, body, {stage: round(seconds, 3) for stage, seconds in stages.items()}


def call(text: str, *, settings, prompt: extract.Prompt, deadline: float,
         post: Post = staged_post) -> dict:
    """One extraction, made as the hook makes it but under `deadline`, and what it cost.

    The row holds no span: a digest of the answer stands in for it, so that two
    answers can be compared without anyone reading either. The digest covers the
    answer as the ledger reads it, its claims and its defects, so two answers
    that differ only in the type a dropped span was given count as one.
    """
    tries, replies = [], []

    def transport(request: extract.Request, timeout_s: float) -> extract.Response:
        tries.append(1)
        status, body, stages = post(request, timeout_s)
        replies.append((status, body, stages))
        return extract.Response(status, body)

    row: dict = {"chars": len(text), "started": _now()}
    started = time.monotonic()
    result = None
    try:
        result = extract.extract(text, prompt=prompt, transport=transport,
                                 settings=dataclasses.replace(settings, timeout_s=deadline))
        row["outcome"] = "usable"
    except extract.ExtractError as e:
        row["outcome"] = "over_deadline" if isinstance(e.__cause__, budget.Overrun) else "failed"
        row["error"] = str(e)[:200]
    except schema.SchemaError as e:
        row.update(outcome="unusable", error=str(e)[:200])
    row["wall"] = round(time.monotonic() - started, 3)
    row["attempts"] = len(tries)
    if replies:              # the thread an overrun abandons may still add one later
        status, body, stages = replies[-1]
        row.update(status=status, stages=stages, **_envelope(body))
    if result is not None:
        answer = [[c.span, c.type, list(c.referents)] for c in result.claims]
        answer += [[d.span, d.reason] for d in result.defects]
        row.update(claims=len(result.claims), defects=len(result.defects),
                   digest=hashlib.sha256(json.dumps(answer, ensure_ascii=False)
                                         .encode("utf-8")).hexdigest()[:12])
    return row


def _envelope(body: bytes) -> dict:
    """What a reply says about how it was made, and nothing of what it says."""
    try:
        envelope = json.loads(body)
    except ValueError:
        return {}
    if not isinstance(envelope, dict):
        return {}
    blocks = [b for b in envelope.get("content") or [] if isinstance(b, dict)]
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    return {"provider": envelope.get("provider"), "stop_reason": envelope.get("stop_reason"),
            "usage": {k: v for k, v in usage.items() if isinstance(v, (int, float))},
            "thinking_tokens": (usage.get("output_tokens_details") or {}).get("thinking_tokens"),
            "blocks": [b.get("type") for b in blocks],
            "text_chars": sum(len(b.get("text") or "") for b in blocks
                              if b.get("type") == "text")}


def plan(reports: Sequence[str], *, passes: int, seed: int = SEED,
         fixed_every: int = FIXED_EVERY) -> list[tuple[int, str]]:
    """The calls of a run, in order: (pass, report), pass 0 for the fixed report."""
    rng = random.Random(seed)
    calls = []
    for number in range(1, passes + 1):
        order = sorted(reports)
        rng.shuffle(order)
        calls += [(number, report) for report in order]
    if not fixed_every:
        return calls
    spaced = []
    for position, item in enumerate(calls):
        if position % fixed_every == 0:
            spaced.append((0, FIXED))
        spaced.append(item)
    return spaced + [(0, FIXED)]


def captured(root: Path, max_chars: int, only: set[str] | None = None) -> dict[str, str]:
    """The reports PROJECT has captured that the extractor would take, by id."""
    reports = {}
    for path in sorted((root / evidence.STATE_DIR / turn.REPORTS).glob("*.md")):
        if only is None or path.stem in only:
            _, text = turn.read_capture(path)
            if len(text) <= max_chars:
                reports[path.stem] = text
    return reports


def reports_of(run: Path) -> set[str]:
    """The captured reports an earlier run asked about."""
    return {row["report"] for row in _rows(run) if row.get("pass")}


def slowdown(row: Mapping) -> float | None:
    """How many times the fast run's time for this answer it took; None for no answer."""
    tokens = (row.get("usage") or {}).get("output_tokens")
    if row.get("outcome") != "usable" or tokens is None:
        return None
    return round(row["wall"] / (FAST_S + FAST_PER_TOKEN_S * tokens), 2)


def slow_now(row: Mapping, previous_slow: bool, *, slow: float, route_deadline: float) -> bool:
    """Whether a probe and the one before it say the route is slow now."""
    this_slow = row.get("slowdown") is None or row["slowdown"] >= slow
    return (this_slow and previous_slow) or row["wall"] >= route_deadline


def measure(out: Path, reports: Mapping[str, str], *, passes: int, seed: int,
            settings, prompt: extract.Prompt, deadline: float, post: Post = staged_post) -> None:
    """Make a run's calls one at a time, appending a row for each as it comes."""
    calls = plan(list(reports), passes=passes, seed=seed)
    with out.open("a", encoding="utf-8") as rows:
        for number, (pass_number, report) in enumerate(calls, 1):
            text = CAPTURED_REPORT if report == FIXED else reports[report]
            row = {"pass": pass_number, "report": report,
                   **call(text, settings=settings, prompt=prompt, deadline=deadline, post=post)}
            rows.write(json.dumps(row) + "\n")
            rows.flush()
            print(f"{_now()[:19]} {number:3}/{len(calls)} {_line(row)}", flush=True)
            time.sleep(PAUSE_S)


def run(args) -> int:
    settings, prompt = _route(args.root)
    only = reports_of(args.same_reports) if args.same_reports else None
    reports = captured(args.root, settings.max_report_chars, only)
    if only is not None and set(reports) != only:
        print(f"{len(only - set(reports))} reports of {args.same_reports} are not captured "
              f"under {args.root} any more", file=sys.stderr)
        return 2
    print(f"{len(reports)} reports, {args.passes} passes, deadline {args.deadline:g}s, "
          f"prompt {prompt.version}, {settings.model} via {settings.provider}", flush=True)
    measure(args.out, reports, passes=args.passes, seed=args.seed, settings=settings,
            prompt=prompt, deadline=args.deadline)
    return 0


def watch(args) -> int:
    settings, prompt = _route(args.root)
    only = reports_of(args.same_reports) if args.same_reports else None
    reports = captured(args.root, settings.max_report_chars, only)
    if args.probe not in reports:
        print(f"{args.probe} is not a captured report under {args.root}", file=sys.stderr)
        return 2
    args.outdir.mkdir(parents=True, exist_ok=True)
    until = time.monotonic() + args.hours * 3600
    seen = _deadline_entries(args.root)
    previous_slow = False
    print(f"probing {args.probe} every {args.every:g}s for up to {args.hours:g}h; slow at "
          f"{args.slow:g}x the fast run", flush=True)
    with (args.outdir / "probes.jsonl").open("a", encoding="utf-8") as probes:
        while time.monotonic() < until:
            row = {"probe": True, "report": args.probe,
                   **call(reports[args.probe], settings=settings, prompt=prompt,
                          deadline=args.deadline)}
            row["slowdown"] = slowdown(row)
            probes.write(json.dumps(row) + "\n")
            probes.flush()
            print(f"{_now()[:19]} probe {_line(row)} x{row['slowdown']}", flush=True)
            if slow_now(row, previous_slow, slow=args.slow, route_deadline=settings.timeout_s):
                print("the route is slow: starting the run", flush=True)
                measure(args.outdir / "run.jsonl", reports, passes=args.passes, seed=args.seed,
                        settings=settings, prompt=prompt, deadline=args.deadline)
                return 0
            previous_slow = row["slowdown"] is None or row["slowdown"] >= args.slow
            next_probe = time.monotonic() + args.every
            while time.monotonic() < min(next_probe, until):
                time.sleep(min(30.0, args.every))
                if _deadline_entries(args.root) > seen:
                    seen = _deadline_entries(args.root)
                    print("a new deadline entry in errors.log: probing now", flush=True)
                    break
    print(f"no slow episode in {args.hours:g}h", flush=True)
    return 0


def summary(args) -> int:
    runs = {path: _rows(path) for path in args.runs}
    for path, rows in runs.items():
        print(f"\n{path}")
        _summarise(rows)
    if len(runs) > 1:
        answers = defaultdict(set)
        for rows in runs.values():
            for row in rows:
                if row.get("pass") and row.get("digest"):
                    answers[row["report"]].add(row["digest"])
        distinct = [len(digests) for digests in answers.values()]
        print(f"\nacross the {len(runs)} runs: {distinct.count(1)} of {len(distinct)} reports "
              f"got one answer every time; distinct answers per report, median "
              f"{statistics.median(distinct):g}, max {max(distinct)}")
    if args.root:
        timed_out = _timed_out_turns(args.root)
        print(f"\nthe {len(timed_out)} reports whose turns passed the deadline in the hook:")
        for report in sorted(timed_out):
            cells = [f"{row['wall']:6.1f}s ({(row.get('usage') or {}).get('output_tokens')} out)"
                     for rows in runs.values() for row in rows
                     if row.get("pass") and row["report"] == report]
            print(f"  {report[:14]}  " + "  ".join(cells))
    return 0


def _summarise(rows: Sequence[Mapping]) -> None:
    probes = [row for row in rows if row.get("probe")]
    if probes:
        factors = [row["slowdown"] for row in probes if row.get("slowdown") is not None]
        if factors:
            print(f"  {len(probes)} probes, {_window(probes)}; slowdown median "
                  f"{statistics.median(factors):g}, under 1.5x in "
                  f"{sum(1 for f in factors if f < 1.5) / len(factors):.0%}")
        print("  probes at 2x or more, or with no answer: "
              + (", ".join(f"{row['started'][11:16]} x{row['slowdown']}" for row in probes
                           if row.get("slowdown") is None or row["slowdown"] >= 2) or "none"))
    real = [row for row in rows if row.get("pass")]
    if not real:
        return
    fixed = [row for row in rows if row.get("report") == FIXED]
    print(f"  {len(rows) - len(probes)} calls, {_window(real + fixed)}; outcomes "
          f"{dict(Counter(row['outcome'] for row in real + fixed))}; providers "
          f"{dict(Counter(row.get('provider') for row in real + fixed))}; with reasoning "
          f"tokens {sum(1 for row in real + fixed if row.get('thinking_tokens'))}; cost "
          f"${sum((row.get('usage') or {}).get('cost', 0) for row in rows):.4f}")
    walls = [row["wall"] for row in real]
    print(f"  {len(real)} calls on captured reports, seconds: "
          + ", ".join(f"p{p} {percentile(walls, p):.1f}" for p in (50, 75, 90, 95, 99))
          + f", max {max(walls):.1f}")
    print("  inside " + ", ".join(f"{limit}s {sum(1 for w in walls if w <= limit)}"
                                  for limit in LIMITS) + f" of {len(walls)}")
    answered = [row for row in real if row["outcome"] == "usable" and row.get("usage")]
    tokens = [row["usage"]["output_tokens"] for row in answered]
    times = [row["wall"] for row in answered]
    if len(set(tokens)) > 1:
        slope, intercept = statistics.linear_regression(tokens, times)
        print(f"  about {intercept:.2f}s + {slope * 1000:.1f}ms per output token "
              f"(r = {_r(tokens, times)}); against report length "
              f"r = {_r([row['chars'] for row in answered], times)}")
    staged = [row for row in answered if row.get("stages")]
    if staged:
        network = [sum(row["stages"][s] for s in ("dns", "tcp", "tls")) for row in staged]
        first = [row["stages"]["first_byte"] for row in staged]
        after = [(row["usage"]["output_tokens"],
                  row["stages"]["api"] - row["stages"]["first_byte"]) for row in staged]
        rates = [tokens / seconds for tokens, seconds in after if tokens > 100 and seconds > 0]
        print(f"  connecting {statistics.median(network) * 1000:.0f}ms median; first byte "
              f"{statistics.median(first):.2f}s median" + (
                  f"; after it, {statistics.median(rates):.0f} tokens/s median, "
                  f"{min(rates):.0f} at the least" if rates else ""))
    passes = defaultdict(list)
    for row in real:
        passes[row["report"]].append(row)
    repeated = [found for found in passes.values() if len(found) > 1]
    same = sum(1 for found in repeated if len({row.get("digest") for row in found}) == 1
               and found[0].get("digest"))
    counts = [[row.get("claims") for row in found] for found in repeated
              if all(row.get("claims") is not None for row in found)]
    differ = sum(1 for c in counts if len(set(c)) > 1)
    doubled = sum(1 for c in counts if max(c) >= 2 * max(1, min(c)))
    with_claims = [row for row in rows if row.get("claims") is not None]
    print(f"  {same} of {len(repeated)} reports got the same answer every pass; the claim "
          f"count differed in {differ}, by two times or more in {doubled}; "
          f"{sum(1 for row in with_claims if row['claims'] == 0)} of {len(rows) - len(probes)} "
          f"answers were empty; {sum(1 for row in with_claims if row['defects'])} carried a "
          f"defect ({sum(row['defects'] for row in with_claims)} against "
          f"{sum(row['claims'] for row in with_claims)} claims kept)")
    if fixed:
        print(f"  fixed report: {len(fixed)} calls, "
              f"{len({row.get('digest') for row in fixed})} distinct answers, "
              f"{sum(1 for row in fixed if row.get('claims') == 0)} empty")


def fixture(args) -> int:
    settings, prompt = _route(args.root)
    payload = json.loads("".join(block["text"] for block in
                                 json.loads(RECORDING.read_text(encoding="utf-8"))["content"]
                                 if block["type"] == "text"))
    recorded = [[c["span"], c["type"], c["referents"]] for c in payload["claims"]]
    print("recorded on 23 September 2026:")
    for span, kind, referents in recorded:
        print(f"   {kind:13} {span!r} {referents}")
    for number in range(1, args.runs + 1):
        started = time.monotonic()
        try:
            result = extract.extract(CAPTURED_REPORT, prompt=prompt,
                                     settings=dataclasses.replace(settings,
                                                                  timeout_s=args.deadline))
        except (extract.ExtractError, schema.SchemaError) as e:
            print(f"run {number}: {type(e).__name__}: {e}")
            continue
        answer = [[c.span, c.type, list(c.referents)] for c in result.claims]
        same = answer == recorded and not result.defects
        print(f"run {number}: {time.monotonic() - started:.1f}s, {result.provenance.provider}, "
              f"{len(result.claims)} claims, "
              f"{'identical to the recording' if same else 'differs from the recording'}")
        for span, kind, referents in answer:
            print(f"   {kind:13} {span!r} {referents}")
        for defect in result.defects:
            print(f"   DEFECT        {defect.span!r} {defect.reason}")
        time.sleep(PAUSE_S)
    return 0


def percentile(values: Sequence[float], p: float) -> float:
    """The p-th percentile, interpolated between the two nearest values."""
    ordered = sorted(values)
    at = (len(ordered) - 1) * p / 100
    low = int(at)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def _r(xs: Sequence[float], ys: Sequence[float]) -> str:
    """Pearson's r to two places, or a dash where one side never varies."""
    try:
        return f"{statistics.correlation(xs, ys):.2f}"
    except statistics.StatisticsError:
        return "-"


def _route(root: Path):
    return config.load(root / config.CONFIG_FILENAME).extractor, extract.load_prompt()


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _deadline_entries(root: Path) -> int:
    try:
        text = (root / evidence.STATE_DIR / "errors.log").read_text(encoding="utf-8")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if "deadline" in line)


def _timed_out_turns(root: Path) -> set[str]:
    try:
        text = (root / evidence.STATE_DIR / "errors.log").read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()     # no turn has failed at all
    reports = set()
    for line in text.splitlines():
        entry = json.loads(line)
        if "deadline" in entry.get("error", ""):
            reports.add(f"{entry['session']}-{entry['turn_number']}")
    return reports


def _line(row: Mapping) -> str:
    stages = row.get("stages") or {}
    return (f"{row['report'][:12]:12} {row['chars']:6} chars {row['wall']:7.2f}s "
            f"{row['outcome']:13} out={(row.get('usage') or {}).get('output_tokens')} "
            f"first_byte={stages.get('first_byte')} api={stages.get('api')}")


def _window(rows: Sequence[Mapping]) -> str:
    started = sorted(row["started"] for row in rows)
    return f"{started[0][:16]} to {started[-1][11:16]} UTC"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Measure the extraction route.")
    commands = parser.add_subparsers(dest="command", required=True)

    def common(sub, *, runs_reports: bool = True):
        sub.add_argument("--root", type=Path, default=Path("."),
                         help="project whose claim-ledger.toml and captured reports are used")
        sub.add_argument("--deadline", type=float, default=150.0,
                         help="wall clock per call, in seconds (default 150)")
        if runs_reports:
            sub.add_argument("--passes", type=int, default=2,
                             help="times each report is asked about")
            sub.add_argument("--seed", type=int, default=SEED, help="seed of the shuffled order")
            sub.add_argument("--same-reports", type=Path,
                             help="ask about the reports of this earlier run and no others")

    measure_one = commands.add_parser("run", help="ask about every captured report")
    common(measure_one)
    measure_one.add_argument("out", type=Path, help="JSONL file the rows are appended to")
    wait = commands.add_parser("watch", help="probe until the route is slow, then run")
    common(wait)
    wait.add_argument("--probe", required=True, help="the captured report to probe with")
    wait.add_argument("--every", type=float, default=300.0, help="seconds between probes")
    wait.add_argument("--slow", type=float, default=2.0, help="slowdown that counts as slow")
    wait.add_argument("--hours", type=float, default=24.0, help="how long to wait at most")
    wait.add_argument("outdir", type=Path, help="where probes.jsonl and run.jsonl go")
    summarise = commands.add_parser("summary", help="summarise one run or several")
    summarise.add_argument("--root", type=Path,
                           help="project whose errors.log names the turns past the deadline")
    summarise.add_argument("runs", type=Path, nargs="+")
    recorded = commands.add_parser("fixture", help="the fixed report against its recording")
    common(recorded, runs_reports=False)
    recorded.add_argument("--runs", type=int, default=3)

    args = parser.parse_args(argv[1:])
    try:
        return {"run": run, "watch": watch, "summary": summary,
                "fixture": fixture}[args.command](args)
    except (config.ConfigError, OSError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

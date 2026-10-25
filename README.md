# claim-ledger

A Claude Code plugin that keeps the harness's own record of what an agent did,
so that the claims in its end-of-turn report can be checked against that
record instead of against the agent's account. Python 3.11+, standard library
only. [docs/OPERATING.md](docs/OPERATING.md) is the one-page note for running it;
the design is in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and
[docs/SPEC.md](docs/SPEC.md); [docs/DECISIONS.md](docs/DECISIONS.md) holds the
reasons that live in neither, and what was tried and rejected on the way.

## What it does now

This is phase 1: the ledger records, audits and reports. It never blocks.

- After every Bash, Edit, Write and NotebookEdit call, succeeded or failed, it
  appends one record to `.claude/claim-ledger/sessions/<session_id>.jsonl`:
  the tool, the command's first line or the file written with its mtime, the
  outcome (`ok`, `failed`, or `unknown` when a command had not finished), the
  turn, and the tier that `claim-ledger.toml` assigns.
- A recorder failure goes to `.claude/claim-ledger/errors.log`, never into the
  session.
- When a turn ends, it captures `.claude/claim-ledger/reports/<session>-<n>.md`:
  the report Claude finished with, and that turn's slice of the evidence log.
  These are the corpus the extractor will be measured against. Set
  `capture = false` under `[corpus]` to stop it.
- Then it audits the turn. The report text, and nothing else, goes to the
  extractor as numbered sentences, and it names the sentences that hold claims,
  with a type each; the span of a claim is its sentence, taken from the report,
  so it is always verbatim. A table-driven join matches those against the
  evidence log and gives
  each one a verdict; no model is involved in that step and none can produce a
  `VERIFIED`. What the report never mentioned is listed beside them.
- The result is one line at the end of the turn, and only more than one line
  when there is something to say:

  ```text
  claim-ledger · 4 verified, 2 unchecked · 2 checks seen · nothing unreported
  ```

  It reaches you and never the model: teaching the agent which claims get
  caught is the one change that would make the whole thing useless.
- Every claim, with its verdict, scope and the extractor route that typed it,
  is appended to `.claude/claim-ledger/claims.jsonl`. Nothing computes a rate
  from it until the sample size declared in the requirements is reached.
- `python3 tools/dump_session.py [SESSION_ID]` prints a session log as a table.
- `python3 tools/annotate_model.py [--only <report>]... [--limit N] [--dry-run] <project>...`
  annotates the corpus with a model, the reference REQUIREMENTS A-12 allows
  since 23 October 2026: `claude-fable-5-1` through the Claude Code CLI, on the
  account the CLI is logged into. Each report the corpus does not hold yet goes
  to it as the extractor gets it, numbered sentences, after the rules of
  [docs/ANNOTATING.md](docs/ANNOTATING.md), and nothing else; the answer is
  checked as a person's would be and appended to `corpus/annotations.jsonl`,
  signed with the model that gave it. `--dry-run` prints what would be sent.
- `python3 tools/annotate.py --by <initials> [--only <report>]... [--older-than 1d] [--corpus <file>] <project>...`
  annotates by hand, which since 23 October serves for the anchor: a few
  reports annotated by a person into `corpus/anchor.jsonl`, which the model's
  annotations are checked against. It asks about each report a sentence at a
  time: a key per claim type, Enter for none, spans typed by hand where one
  sentence holds two claims. It shows the report and nothing else, neither the
  evidence nor the extractor's claims, and appends one line per finished
  report. `--older-than` keeps back the reports captured too recently, while
  the line that ended each turn is still in mind.
- `python3 tools/extract_report.py <report.md>` runs the extractor over one
  captured report and prints the claims it finds, to compare against the
  report's annotation once that is written. It needs whichever variable
  `[extractor] key_env` names (`OPENROUTER_API_KEY` in the sample config);
  `--request` prints what would be sent and sends nothing.
- `python3 tools/measure_route.py run|watch|summary|fixture` measures the
  extraction route over a project's captured reports: how long each call takes,
  stage by stage, and whether the same report gets the same answer twice.
  `watch` probes until the route turns slow and measures it then. It keeps
  timings and a digest of each answer, and with `run --corpus` the answers too,
  as sentence numbers and types, for the reports the corpus annotates.
  `--config` measures another route from a copy of the project's
  `claim-ledger.toml`, and `--prompt` another prompt file, while the hook goes
  on sending its own. It needs the same key as `extract_report.py`. What it
  found on 17 October 2026 is in
  [docs/provider-measurements.md](docs/provider-measurements.md).
- `python3 tools/measure_recall.py agreement|recall` scores, and makes no call.
  `agreement` sets the model's annotations against the anchor in both
  directions, on checkable claims, and names every sentence the two typed
  differently. `recall` scores runs made with `run --corpus`, one file to a
  candidate: each pass's recall, spurious share and `UNKNOWN` share, the
  candidate judged by its worst pass against the phase-1 threshold, and every
  claim a pass missed. A line names a report, a sentence number and types;
  `--spans` adds the sentence.
- `python3 tools/daily_use.py recording|latency|verdicts|defects` reads back
  what daily use recorded: whether every tool call in a session's transcript
  has its record, how long each Stop took and how its turn ended, an empty
  answer included, which `VERIFIED` claims a person should read, and how the
  spans the extractor got wrong differ from the report. It prints spans only
  with `--spans`, and makes no call.

## What it does not do yet

- **The extractor does not clear phase 1.** Three candidate routes ran the
  corpus three times each on 24 October 2026, and the best reached recall 0.67
  on checkable claims, where phase 1 needs 0.90 over at least 50 annotated
  reports. The reference is a model's annotation, which agrees with the
  reports a person annotated by hand on about three checkable claims in four
  ([docs/DECISIONS.md](docs/DECISIONS.md)). Read the appendix as an instrument
  that, measured so, misses a third of the checkable claims.
- Nothing blocks a turn, and in v1 nothing ever will. Blocking is phases 2 and
  3, and each is gated on evidence from the phase before it.
- Nothing aggregates several claims in one sentence into one verdict. Each
  claim carries its own, and the appendix lists them separately.

## Tests

```bash
python3 tools/run_suite.py
```

**Declared versions: 3.11, 3.12, 3.13, 3.14.** The set lives in `tools/run_suite.py`
and nowhere else; the pre-commit hook and CI both go through that script. A
declared version that is not installed is a named failure and stops the run —
the suite never reports a pass on fewer versions than it claims. Each one is
resolved from PATH first and then through uv, and the script says which
answered, because asking PATH and asking uv give different answers about the
same machine:

```text
claim-ledger · declared: 3.11, 3.12, 3.13, 3.14

  3.11  system  Ran 321 tests in 5.946s OK                             6.1s
  3.12  system  Ran 321 tests in 6.271s OK                             6.4s
  3.13  system  Ran 321 tests in 5.935s OK                             6.0s
  3.14  system  Ran 321 tests in 5.926s OK                             6.0s

all 4 declared versions passed
```

`--list` shows where each version was found without running anything. Install a
missing one with `uv python install <version>`; uv is only needed for versions
that are not on PATH, and the script never downloads one behind your back.

**3.11, the floor the project supports, is declared like the rest.** It used to
be left to a CI job of its own, but this repository has never had a remote, so
that job never ran and the floor was claimed without being tested. The
pre-commit hook runs on every commit; CI runs only where something is pushed.

Enable the hook once per clone:

```bash
git config core.hooksPath .githooks
```

The suite makes no network call and no model call, and neither the tests nor
the hooks write to `.claude/claim-ledger/`.

## Install

1. Write `claim-ledger.toml` at the project root. The one in this repository
   is a sample. Which commands are checks and which paths are consequential is
   for you to decide.
2. Run `python3 <plugin>/src/ledger/install.py <project>`. This adds the deny
   rule `Edit(claim-ledger.toml)` to `.claude/settings.json` (commit it, so
   that every clone gets it), and adds `.claude/claim-ledger/` to `.gitignore`
   unless git ignores that directory already.
3. Start Claude Code at the project root with `claude --plugin-dir <plugin>`.

While git would commit `.claude/claim-ledger/`, the plugin writes nothing and
says so on every tool call. Whether git would is git's answer, so ignoring
`.claude/` wholesale counts; outside a repository there is nothing to commit
and it records as usual. The `python3` on your PATH must be 3.11 or later; see
Tests above for the versions the suite is declared to pass on.

## Known gaps

- **Cancelled tool calls leave no record.** A call the user cancels fires
  neither hook.
- **Secrets passed any way but a leading assignment are stored.** The value of
  a leading `NAME=value` is masked. `--token=…`, `export NAME=…`,
  `env NAME=…` and assignments after `&&` are stored as written.
- **Turns that end without a Stop event get no appendix.** This covers a user
  interrupt, and an API error, which fires StopFailure instead. Those turns are
  recorded in the evidence log like any other, and are simply never audited:
  the silence means the hook did not run, not that the turn was clean.
- **A turn whose `claim-ledger.toml` cannot be read is not captured either.**
  Whether to capture is a setting in that file, so a config that fails to load
  takes the capture with it. The turn is `UNKNOWN` and says so.
- **The configuration hash is taken when the ledger first runs in a session**,
  not when the session opens, because the earliest the plugin exists in a
  session is its first hook. A change made before that first hook is not
  detectable from this side.
- **Files written by Bash commands get no `files` entry.** Freshness is
  unaffected, because it reads mtimes from disk.
- **Subagent tool calls are recorded like the main thread's**, with no
  `agent_id` to tell them apart.
- **The freshness scan walks the whole working tree, once a turn.** The first
  claim that needs it pays for the walk, a second or more where a virtual
  environment sits in the project, and every other claim of the turn is judged
  against the same listing. It has never been run against a large repository.
  It is bounded by the turn budget, so where it is slow the turn goes `UNKNOWN`
  rather than over time — visible, but not fast.
- **Windows paths have never been exercised.**
- **The session must start at the project root.** `.claude/settings.json` and
  the deny rule are read from the directory Claude Code starts in.
- **One lost record makes every later turn of that session `UNKNOWN`.** An
  entry in `errors.log` means the evidence log has a hole in it, and a log with
  a hole cannot be joined against honestly — not for the turn that lost the
  record and not for a later one. The condition is the session's, so it is
  sticky by design; starting a new session clears it.
- **The log and the configuration can be written by any process the agent
  starts.** This is accepted, not defended against; see Threat model in the
  requirements.
- **An answer the client cannot read makes the turn `UNKNOWN`.** Nothing is
  repaired. The endpoint is asked to enforce the answer's shape with a JSON
  schema, which ends code fences and stray keys at the source; it cannot know
  how many sentences the report has, so validation still runs and a number
  naming no sentence is still counted as a defect.
- **A slow model costs turns.** The call has a wall-clock deadline that fits
  inside the turn budget, and one that passes it is `UNKNOWN`. One run in
  fourteen passed it when the route was measured; in daily use, 11 turns in 44
  did up to 17 October 2026, 9 of them in the 22 since 10 October. See
  [docs/DECISIONS.md](docs/DECISIONS.md).

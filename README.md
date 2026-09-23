# claim-ledger

A Claude Code plugin that keeps the harness's own record of what an agent did,
so that the claims in its end-of-turn report can be checked against that
record instead of against the agent's account. Python 3.11+, standard library
only. The design is in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and
[docs/SPEC.md](docs/SPEC.md).

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
  extractor, which returns the claims it holds as verbatim spans with a type
  each. A table-driven join matches those against the evidence log and gives
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
- `python3 tools/extract_report.py <report.md>` runs the extractor over one
  captured report and prints the claims it finds, so a corpus can be annotated
  against real output. It needs whichever variable `[extractor] key_env` names
  (`OPENROUTER_API_KEY` in the sample config); `--request` prints what would be
  sent and sends nothing.

## What it does not do yet

- **The extractor has not been measured.** There is no annotated corpus and no
  recall figure, so the appendix should be read as an instrument still being
  calibrated. Phase 1 clears when recall on checkable claims reaches 0.90 over
  at least 50 annotated reports.
- Nothing blocks a turn, and in v1 nothing ever will. Blocking is phases 2 and
  3, and each is gated on evidence from the phase before it.
- Nothing aggregates several claims in one sentence into one verdict. Each
  claim carries its own, and the appendix lists them separately.

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
and it records as usual. The `python3` on your PATH must be 3.11 or later.

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
- **Subagent tool calls are recorded like the main thread's.**
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
  schema, which ends code fences and stray keys at the source; it cannot make
  a span verbatim, so validation still runs and defects are still counted.
- **A slow model costs turns.** The call has a wall-clock deadline that fits
  inside the turn budget, and one that passes it is `UNKNOWN`. On the route in
  use, one run in fourteen measured that way.

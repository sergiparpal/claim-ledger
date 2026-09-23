# claim-ledger

A Claude Code plugin that keeps the harness's own record of what an agent did,
so that the claims in its end-of-turn report can be checked against that
record instead of against the agent's account. Python 3.11+, standard library
only. The design is in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and
[docs/SPEC.md](docs/SPEC.md).

## What it does now

This is phase 0: the evidence log and the corpus capture, nothing else.

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
- `python3 tools/dump_session.py [SESSION_ID]` prints a session log as a table.
- `python3 tools/extract_report.py <report.md>` runs the extractor over one
  captured report and prints the claims it finds, so a corpus can be annotated
  against real output. It needs `ANTHROPIC_API_KEY`; `--request` prints what
  would be sent and sends nothing.

## What it does not do yet

- Nothing extracts by itself. The extractor exists and can be run by hand, but
  the Stop hook still only captures the turn; no verdict is computed and no
  appendix is shown until the extractor has been measured against a corpus.
- The configuration hash check (I-8) is not built. The deny rule is the only
  protection so far, and it only stops the Edit tool.
- Nothing blocks a turn, and in v1 nothing ever will.

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
  interrupt, and an API error, which fires StopFailure instead. It will stay
  true after the appendix exists.
- **Files written by Bash commands get no `files` entry.** Freshness is
  unaffected, because it reads mtimes from disk.
- **Subagent tool calls are recorded like the main thread's.**
- **The session must start at the project root.** `.claude/settings.json` and
  the deny rule are read from the directory Claude Code starts in.
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

# Running claim-ledger day to day

One page. The rest is in [REQUIREMENTS](REQUIREMENTS.md) and [SPEC](SPEC.md).

## Start a session

```bash
cd <your project> && claude --plugin-dir ~/code/claim-ledger
```

Once per project first: `python3 ~/code/claim-ledger/src/ledger/install.py <project>`,
and copy `claim-ledger.toml` to the project root. That file is yours — which
commands count as checks, which paths are consequential. The ledger never guesses
at it and never writes to it.

Nothing at the end of a turn means the plugin is not loaded, or git would commit
`.claude/claim-ledger/`. The second says so on every tool call; the first is
silent, so check `--plugin-dir` and that you started at the project root.

## Reading the line

```text
claim-ledger · 4 verified, 2 unchecked · 2 checks seen · nothing unreported
```

All clear. **verified** matched a record in the evidence log. **unchecked** are
opinions and intentions — no evidence contract, never listed back at you.
**checks seen** is how many checks the session ran, printed even at zero, which
is when it says most.

Anything else expands, worst first:

| Group | Means |
| --- | --- |
| `CONTRADICTED` | the log says that check failed — stands alone at the head |
| `UNKNOWN` | no verdict could be computed; see below |
| `STALE` | it passed, then something it covers changed. Re-run, or reword |
| `UNSUPPORTED` | nothing in the log matches |
| `UNREPORTED` | the turn did this and the report never said so. Tier in brackets; `LOW` counted, not listed |
| `EXTRACTION DEFECTS` | a span came back that is not in the report — an extractor error, not an agent one |

`UNSUPPORTED` on something you watched succeed is usually the alias table. "the
tests pass" names the referent *tests*, and `[checks.aliases]` must map that exact
wording to a check id. The ledger will not guess: resolving an unknown name to
whatever happened to run is how a claim about the integration tests gets verified
against a unit run. Widen the aliases deliberately, from what reports actually
say, not one at a time.

If the line also says `0 checks seen`, no alias will help: nothing the session
ran matched an invocation in `[checks]`, either because none is declared or
because every run carried a pipe, a `;` or a `&&`, and a command with a shell
operator is never a check.

A turn that lists no claim and ends `0 verified, 0 unchecked`, under a report
that plainly claims things, got an empty list from the extractor, which the
route was first seen doing on 17 October 2026 ([DECISIONS](DECISIONS.md)). Each
`UNREPORTED` line on it is then the extractor's omission, not the report's. With
nothing to list, the same answer prints the collapsed line, and there
`0 verified, 0 unchecked` vouches for nothing.

Nothing ever blocks. Phase 1 observes and reports.

## UNKNOWN turns

```text
claim-ledger · UNKNOWN · ExtractError: the model call passed its 12.0s deadline · 1 check seen
```

No verdict was computed — it says nothing about your work. The reason is on the
line; the full entry is in `.claude/claim-ledger/errors.log`. In the order you
will meet them:

- **The model call timed out or failed.** Nothing to do on the turn, but it is
  not occasional: one run in fourteen passed the deadline when the route was
  measured, and 11 turns in 44 did in distiller up to 17 October 2026, 9 of them
  since 10 October. Whether the deadline moves is open; see
  [DECISIONS](DECISIONS.md).
- **`claim-ledger.toml` changed mid-session.** Fine if you edited it. Worth a hard
  look if you did not. A new session re-baselines.
- **A record was lost** (`component: record` in `errors.log`). Every later turn of
  that session stays UNKNOWN: the log has a hole and the join would read across
  it. A new session clears it.
- **No `OPENROUTER_API_KEY`** in the environment. Claude Code does not inherit it
  here — it lives in `~/.config/claim-ledger/env` (mode 600), which `~/.bashrc`
  loads in an interactive shell and a hook never reads. Export it before
  starting Claude Code, not after. A one-off command that needs it can load the
  file itself:

  ```bash
  . ~/.config/claim-ledger/env
  ```

- **HTTP 401 from the model call.** The key arrived and OpenRouter refused it,
  answering "User not found": the key was revoked or deleted. Make a new one and
  write it into `~/.config/claim-ledger/env`, and into any
  `.claude/settings.local.json` that holds a copy under `env`.

The report is still captured. Nothing is lost for the corpus.

## Where the corpus accumulates

```text
.claude/claim-ledger/          (under the project, never committed)
├── reports/<session>-<n>.md   one per turn: the report and that turn's evidence
├── sessions/<session>.jsonl   the evidence log
├── claims.jsonl               every claim, verdict and route, for calibration
└── errors.log                 why a turn was UNKNOWN
```

`reports/` is the corpus. It fills on every turn ending in a Stop event — so not
one you interrupt, and not one that dies on an API error. `capture = false` under
`[corpus]` turns it off.

## Counting what you have

```bash
ls .claude/claim-ledger/reports/*.md 2>/dev/null | wc -l
```

Across every project that has run the plugin:

```bash
find ~ -path '*/.claude/claim-ledger/reports/*.md' 2>/dev/null | wc -l
```

The target is **50 annotated reports**, clearing recall 0.90 on checkable claims,
spurious extractions at or below 0.10, and no non-verbatim span. Declared before
the extractor existed; it does not move, and since 23 October 2026 it is
measured against a model's annotations (REQUIREMENTS A-12). The model annotates
with:

```bash
python3 ~/code/claim-ledger/tools/annotate_model.py <project> [<project>...]
```

It sends each report the corpus does not hold yet to `claude-fable-5-1` through
the Claude Code CLI, on the account the CLI is logged into, and appends the
checked answer to `corpus/annotations.jsonl`. A report it cannot trust the
answer for is named and left for the next run; `--dry-run` prints what would
be sent and sends nothing.

A few reports annotated by hand are the model's anchor, kept in a file of their
own:

```bash
python3 ~/code/claim-ledger/tools/annotate.py --by <initials> --corpus ~/code/claim-ledger/corpus/anchor.jsonl --only <report> [--only <report>]... <project>
```

It asks a sentence at a time: `1`–`5` for the type, Enter for no claim, `s` to
type the spans when one sentence holds two claims, `n` to leave a report for
another run, `q` to stop. A report is written only once it is finished. It
shows the report and nothing else. What to mark, and the rules for the hard
cases, are in [ANNOTATING](ANNOTATING.md). Do not read the model's annotations
of the anchor's reports before annotating them, for the reason that follows. Run
`python3 tools/extract_report.py <report.md>` on a report after annotating it,
never before: an annotator who has seen the extractor's list confirms it, and
the claims it missed are the ones recall counts.

Once the anchor is annotated, `agreement` says how far the model agrees with
it. Each candidate route then runs the corpus three times, from a copy of the
project's `claim-ledger.toml` with that route under `[extractor]`, and
`recall` scores the runs against the corpus:

```bash
python3 ~/code/claim-ledger/tools/measure_recall.py agreement --root <project>
python3 ~/code/claim-ledger/tools/measure_route.py run --root <project> --config <route.toml> --corpus ~/code/claim-ledger/corpus/annotations.jsonl --passes 3 <run.jsonl>
python3 ~/code/claim-ledger/tools/measure_recall.py recall --root <project> <run.jsonl> [<run.jsonl>...]
```

The run calls the route three times a report and needs the key; the other two
call nothing. The figures are in [DECISIONS](DECISIONS.md): no route measured
clears phase 1, and with the prompt the hook sends since 25 October 2026 the
route in use misses a quarter of the checkable claims the annotator marks.
Read the appendix as an instrument that does.

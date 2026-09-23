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

Nothing ever blocks. Phase 1 observes and reports.

## UNKNOWN turns

```text
claim-ledger · UNKNOWN · ExtractError: the model call passed its 12.0s deadline · 1 check seen
```

No verdict was computed — it says nothing about your work. The reason is on the
line; the full entry is in `.claude/claim-ledger/errors.log`. In the order you
will meet them:

- **The model call timed out or failed.** Expected occasionally, about one run in
  fourteen on the measured route. Nothing to do.
- **`claim-ledger.toml` changed mid-session.** Fine if you edited it. Worth a hard
  look if you did not. A new session re-baselines.
- **A record was lost** (`component: record` in `errors.log`). Every later turn of
  that session stays UNKNOWN: the log has a hole and the join would read across
  it. A new session clears it.
- **No `OPENROUTER_API_KEY`** in the environment. Claude Code does not inherit it
  here — it is exported at line 131 of `~/.bashrc`, which an interactive shell
  reads and a hook does not. Export it before starting Claude Code, not after.
  A one-off command that needs it can load that one line:

  ```bash
  eval "$(grep -E '^[[:space:]]*export[[:space:]]+OPENROUTER_API_KEY=' ~/.bashrc)"
  ```

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
the extractor existed; it does not move. Annotate by hand into
`corpus/annotations.jsonl`; `python3 tools/extract_report.py <report.md>` prints
what the extractor found for one report, so you annotate against real output
rather than memory.

Until that corpus exists there is no recall figure, and the appendix is an
instrument nobody has calibrated. Read it as one.

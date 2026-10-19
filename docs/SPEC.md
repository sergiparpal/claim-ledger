# Claim Ledger — Technical Spec, Phases 0 and 1

2026-09-19 · @Someone

## Scope

This spec covers phases 0 and 1 of the requirements document: the evidence log, the extractor, the join, and the appendix. Nothing here blocks a turn.

**Fixed for this build**

| Decision | Value |
| --- | --- |
| Evidence log location | one JSONL file per session under `.claude/claim-ledger/sessions/`, gitignored |
| Record ordering | position in the file. No counter and no lock: single `O_APPEND` writes hold, a shared counter would not |
| Staleness source | log order plus the current mtimes of the files a check covers, read at join time. Either test can make a check stale |
| Outcome | `ok`, `failed` or `unknown`, taken from which hook event fired, never parsed out of an error string |
| Extractor calls | one per turn, behind an interface that allows two later (R-14) |
| Claim types | `command_run`, `suite_passed`, `file_changed`, `judgment`, `intent` |
| Config protection | hash at session open, recheck at turn end, `UNKNOWN` on change |

**Deferred, and why they do not block this build**

- Fail-open or fail-closed only matters once something can block.
- `HUMAN`-tier acknowledgement belongs to phase 3.
- The recall threshold is declared before the first measurement, not before the code.

**Requirements covered here:** R-1 to R-29, R-34 to R-45, and I-1 to I-10. R-30 to R-33 are the gate itself: specified in the requirements document, implemented in phases 2 and 3. R-25 is here because the tier matching the gate will use is what phase 1 already needs to decide which actions are consequential. Last edited 19 October 2026, when the corpus measurement came to report, beside recall, the share of checkable claims whose referents the join could match (§ Corpus capture); the day before, it came to run each candidate three times and judge it by its worst pass, and the extractor moved to the sentence contract, the report going out as numbered sentences and the answer naming them by number (§ Extractor contract): a copy of this document without this sentence is stale.

**Revised 19 September 2026**, after the step-1 session verified the hook payloads and measured concurrent appends. What changed: the record dropped its counter and its exit code, gained an outcome and a turn id; freshness moved to join time; `[checks]` takes exact invocations instead of globs; config protection became detection rather than prevention.

## Plugin layout

One Claude Code plugin, Python 3.11+, standard library only outside the extractor's HTTP call. Everything it writes stays under the project.

```text
claim-ledger/
├── hooks/hooks.json           the three hook registrations
├── src/ledger/
│   ├── config.py              load and validate claim-ledger.toml
│   ├── record.py              PostToolUse handler: append one evidence record
│   ├── evidence.py            log writer and reader, nothing else
│   ├── extract.py             extractor client behind one interface
│   ├── schema.py              claim list schema and validation
│   ├── join.py                referent matching and the verdict table
│   ├── coverage.py            consequential actions the report never mentions
│   ├── appendix.py            rendering, collapsed and expanded
│   ├── budget.py              the turn's wall clock, and abandoning a slow stage
│   ├── turn.py                Stop handler: the pipeline, end to end
│   └── calibration.py         the durable claims-and-verdicts log
├── tests/
│   ├── fixtures/              synthetic sessions: evidence log + report text
│   ├── doubles.py             recorded extractor responses, no HTTP
│   └── test_*.py
├── claim-ledger.toml          the user's configuration, committed
└── README.md
```

Runtime state, none of it committed:

```text
.claude/claim-ledger/
├── sessions/<session_id>.jsonl      the evidence log
├── reports/<session_id>-<n>.md      captured reports, phase 0 onwards
├── claims.jsonl                     the calibration log
└── errors.log                       pipeline failures, with their turn ids
```

The plugin adds `.claude/claim-ledger/` to the project's `.gitignore` on install, and refuses to run when git reports the directory is not ignored, which is the question that actually matters.

## Configuration

One TOML file at the project root, written by the user. Every pattern the system matches on comes from here: nothing is inferred from the repository.

```toml
[checks]
# Exact invocations that count as a full run of each check. No globs:
# "pytest*" also matches "pytest --version", which is a route to a
# false VERIFIED. A command that does not match exactly is not a check,
# and the claim lands as UNSUPPORTED — the safe direction.
python-suite = ["pytest", "pytest -q", "python -m pytest", "uv run pytest"]
js-suite     = ["npm test"]
types        = ["mypy src"]
lint         = ["ruff check ."]

[checks.scope]
# which files each check covers, for the freshness rule
python-suite = ["src/**/*.py", "tests/**/*.py"]
js-suite     = ["src/**/*.ts"]
types        = ["src/**/*.py"]
lint         = ["**/*"]

[checks.aliases]
# the words reports actually use for a check, mapped to the check they mean
"unit test"  = "python-suite"
"unit tests" = "python-suite"
"the tests"  = "python-suite"
"the suite"  = "python-suite"

[tiers]
# used in phase 1 to decide which actions are consequential enough
# that not mentioning them is worth reporting
HUMAN   = ["migrations/**", "deploy/**", "Bash(git push*)", "Bash(*rm -rf*)"]
LOW     = ["docs/**", "**/*.md"]
default = "REVIEW"

[extractor]
# OpenRouter's Anthropic-shaped endpoint, which takes the same request schema.
# Both x-api-key and Authorization: Bearer were verified to work there.
base_url         = "https://openrouter.ai/api/v1"
auth             = "x-api-key"
key_env          = "OPENROUTER_API_KEY"
model            = "deepseek/deepseek-v4.1-flash"
# Twenty-two providers serve this model. Exactly one, with fallbacks off, is
# what makes a recall figure mean anything. Morph is the only one found that
# honours the thinking switch below; its quantization is undeclared, which is
# the price of the switch working.
provider         = "morph"
answer_shape     = "json_schema"
# A deadline over the whole call, not a socket timeout, and it has to fit
# inside [budget] below, which the loader checks.
timeout_s        = 12
max_report_chars = 20000

[extractor.parameters]
# What this route takes, sent as written. Which sampling parameters a model
# accepts is a fact about the route: GPT-5.x takes neither temperature nor
# top_p, and with require_parameters on, one it refuses leaves the router with
# no endpoint at all — a 404 before the model is ever reached.
temperature = 0

# Thinking off, through the provider's own chat template rather than the
# reasoning parameter, and verified against the reply rather than the status.
[extractor.parameters.extra_body.chat_template_kwargs]
enable_thinking = false

[budget]
# The pipeline's own wall clock. Strictly longer than [extractor] timeout_s,
# which the loader checks, and strictly shorter than the Stop hook's timeout in
# hooks/hooks.json, which is when the harness kills the process. That second
# gap is what the UNKNOWN gets rendered in.
turn_timeout_s = 15

[log]
max_command_chars = 2000

[gate]
enabled = false   # phase 2 flips this. Present from the start: the loader
                  # rejects unknown keys, so adding it later is a migration

[corpus]
capture = true
```

- Check matching is exact, after stripping surrounding whitespace. A separate aliases table maps the words a report actually uses, such as the unit test or the tests, to a check id, because a referent that names something and resolves to nothing must stay unsupported: resolving it to whatever check the session happened to run would verify a claim about the integration tests against a unit run. A command containing a shell operator is never a check, and an unlisted invocation is not one either. Missing a real run costs a `VERIFIED`; matching the wrong one manufactures a false one.
- Tier precedence: `HUMAN` beats `LOW` beats the default; within a tier, first match wins in file order. The two tiers match by opposite rules, and both err the same way. `HUMAN` matches **any part** of a compound command, deliberately over-matching: `cd app && timeout 60 git push` meets `Bash(git push*)`. `LOW` applies only when a `LOW` entry covers **every part** of the action — each path it touched, each segment of the command — because `LOW` is the tier that stops an action being listed as unreported, and one that is only partly cheap is not cheap. An action that is half `docs/**` and half `src/**` takes the default. Simplifying either half to "matches somewhere" would make `LOW` the easiest tier to fall into rather than the hardest.
- Command patterns use Claude Code's permission-rule syntax, so they read the same as the deny rules beside them.
- A missing or invalid config is a hard startup failure with the offending key named. A scope entry containing whitespace is invalid for the same reason: it can never match a path, and a scope that cannot match leaves the session with no checks at all, silently. It never falls back to defaults, because a silent default here decides what counts as consequential.
- Protection (R-27, I-8): the file's hash is taken when the session opens and rechecked at the end of every turn; a change marks the turn `UNKNOWN` and says so. The install also writes a deny rule for `Edit(claim-ledger.toml)`, which stops the obvious route and nothing else — a Python one-liner from Bash writes the file regardless.

## Evidence log

One JSONL file per session, one object per tool call, appended and flushed as it happens. The file is the only input to the join.

```json
{"v": 2,
 "session": "abc123",
 "turn_id": "550e8400-...",
 "turn_number": 3,
 "tool_use_id": "toolu_01ABC",
 "tool": "Bash",
 "kind": "check",
 "command": "pytest -q",
 "check_id": "python-suite",
 "outcome": "failed",
 "outcome_detail": "Exit code 1",
 "ts_end": "2026-09-19T14:32:07.880Z",
 "duration_ms": 6660,
 "tier": "REVIEW"}
```

A mutation record carries `files` instead of `command` and `check_id`: `[{"path": "src/engine.py", "mtime": "2026-09-19T14:35:12.004Z"}]`, with the path taken from the tool's input, never from its response, since the responses of all three file tools carry file contents.

| Field | Rule |
| --- | --- |
| `outcome` | `ok` from `PostToolUse`, `failed` from `PostToolUseFailure`, `unknown` when the call may still be running — a Bash response carrying a background id, a background flag, an interrupted flag or a timeout field means the command was not finished when the hook fired, and a timed-out suite recorded as `ok` would verify a claim about tests that never completed |
| `outcome_detail` | the first line of the harness's error string, kept verbatim, never parsed, truncated at `log.max_command_chars`. The rest of that string is the command's own output and would carry file contents and secrets into the log (R-7) |
| `kind` | `check` when the command matches an entry in `[checks]`, `mutation` for `Edit`, `Write` and `NotebookEdit`, `other` otherwise |
| `check_id` | present only on `check` records, straight from the config |
| `turn_id` | the harness's prompt id, and nothing else. `null` when the payload carried none, which is the case before the first prompt and on a CLI older than v2.1.196. It is never a counter: the same word meaning two things in the log and in a captured report is what the join has to cross at step 8 |
| `turn_number` | the session's own count of turns, always present. The recorder reads it from `sessions/<session>.turn` and treats a missing file as turn 1; it never writes that file, because a counter the recorder incremented would be the read-modify-write this design forbids. The Stop handler advances it once per turn, and names the captured report `<session>-<turn_number>.md` |
| `ts_end` | when the record is written, which is when the hook fires. No hook payload carries a start time; `duration_ms` is recorded when supplied |
| `files` | mutation records only: the path from `tool_input`, with its mtime read by `stat` after the call returns |
| `tier` | resolved at write time from the config, so the log stays readable without it |

- **Ordering is file position.** Records carry no counter. Concurrent `PostToolUse` hooks appending with a single `O_APPEND` write do not interleave, but computing a shared counter across them needs a lock, and a lock that sticks would blow the recorder's timeout and lose records — which is the one failure this system must not have.
- One `write` call per record, under 4 KB in practice. No read-modify-write, ever.
- The record is version 2. Version 1 held a single `turn` field that fell back to the counter; the reader refuses those logs rather than reading them as if they matched, since two shapes under one version number is how a join goes quietly wrong.
- Timestamps are UTC, ISO 8601, millisecond precision, from the local clock, the same one the filesystem stamps mtimes with.
- Commands are stored truncated at the first newline and at `log.max_command_chars`, which keeps heredocs and their contents out of the log (R-7). File contents and environment variables are never stored, and the value of a leading `NAME=value` assignment is replaced by a marker, keeping the name. A secret passed as a flag, `--token=…`, is not caught: that is a known limit, written down rather than assumed away.
- A recorder that fails writes one line to `errors.log` and exits 0, and writes no partial record. The turn handler reads that file for the current session, and any entry makes the turn `UNKNOWN` (I-9). A lost record must never look like an action that did not happen.
- **Known gaps.** A tool call the harness refuses, the user cancels, or never runs fires neither hook and leaves no record, so coverage cannot report it. A claim about one lands as `UNSUPPORTED`, which is the safe direction. Separately, two concurrent writes to the same file may be recorded in the order their hooks fired rather than the order they happened. That does not affect freshness, where only the check's own position matters, but it means the log is not a narrative of what happened second by second.

## Hook wiring

Three registrations, all command hooks, all in `hooks/hooks.json`.

```json
{
  "description": "Claim ledger: record evidence, audit the turn's claims",
  "hooks": {
    "PostToolUse": [
      { "matcher": "Bash|Edit|Write|NotebookEdit",
        "hooks": [{ "type": "command", "command": "python3",
                    "args": ["${CLAUDE_PLUGIN_ROOT}/src/ledger/record.py"],
                    "timeout": 5 }] }
    ],
    "PostToolUseFailure": [
      { "matcher": "Bash|Edit|Write|NotebookEdit",
        "hooks": [{ "type": "command", "command": "python3",
                    "args": ["${CLAUDE_PLUGIN_ROOT}/src/ledger/record.py"],
                    "timeout": 5 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3",
                    "args": ["${CLAUDE_PLUGIN_ROOT}/src/ledger/turn.py"],
                    "timeout": 20,
                    "statusMessage": "Auditing the turn's claims" }] }
    ]
  }
}
```

**Why `PostToolUseFailure` too, and where `outcome` comes from.** Confirmed against the hooks reference: `PostToolUse` fires only when the tool succeeds, and for Bash its `tool_response` carries stdout, stderr and an interrupted flag, with no exit code anywhere. A non-zero shell exit arrives at `PostToolUseFailure` instead, with `Exit code N` as the first line of `error`, a string the reference says is not a stable format and that some failures omit. So `outcome` is decided by which event fired, and the first line of the error string is stored as detail and never parsed. `CONTRADICTED` depends on this, which is why the failure event carries the same handler.

**The recorder** reads the event JSON on stdin, resolves `kind`, `check_id` and `tier` from the config, `stat`s the written file on mutation events, appends one record, and exits 0 with no output. It never writes to stdout: on `PostToolUse` stdout goes to the debug log, and text there would be noise. On its own failure it appends to `errors.log` and still exits 0, so a broken recorder never interferes with the session, and the turn is marked `UNKNOWN` when the pipeline reads that log.

The one exception is the refusal. With the gitignore line missing, `errors.log` would itself sit in an unignored directory, so the recorder writes nothing at all and returns a `systemMessage` instead, which reaches the user on every tool call until the line is there. The turn handler treats an active refusal as `UNKNOWN` for the same reason it treats an error entry that way: an empty log and a refused log look identical from the outside.

**The turn handler** runs the whole phase-1 pipeline: read the report from `last_assistant_message`, extract, join, render, write the calibration rows. It exits 0 and returns the appendix as `systemMessage`, which is what puts it in front of the user.

- Never exit 2 in v1. On `Stop`, exit 2 prevents Claude from stopping and continues the conversation, which is exactly the gate, and the gate is phase 2.
- Read the report from `last_assistant_message`, never from `transcript_path`: the transcript file is written asynchronously and may lag the turn that just ended.
- All three events supply `session_id`, `transcript_path`, `cwd`, `hook_event_name` and `permission_mode`. `prompt_id` needs a recent CLI and is absent before the first prompt, which is why the recorder keeps its own per-session counter as a fallback.
- No payload carries a start time, so R-2's start field is optional and `duration_ms` stands in where the harness supplies it.
- `Stop` does not fire when the user interrupts, and an API error fires `StopFailure` instead. Those turns get no appendix at all. The README says so plainly rather than leaving the silence to be discovered.
- `systemMessage` is capped at 10,000 characters. The collapsed appendix keeps a normal turn far under it; the expanded one truncates spans to fit and says how many entries it dropped.
- **The hook's timeout is not the budget, and it is strictly larger.** `[budget] turn_timeout_s` is 15: the pipeline's own wall clock, which it watches and reports overrunning as `UNKNOWN`. The hook's timeout is 20: when the harness kills the process. Equal values, which is what shipped until 23 September 2026, leave nothing between the two — the pipeline would notice it had run out of budget at the same instant it was killed, and the `UNKNOWN` it exists to report would be what the kill destroyed. The five seconds are the room to render it. A cancelled hook renders no decision at all, which is why the margin is real time rather than an assumption about how fast rendering is.

## Extractor contract

One function, one call per turn, no state. Its isolation is the whole point of I-1, so the interface makes the isolation checkable rather than intended.

```python
def extract(report_text: str, *, vocabulary: list[str], settings: Extractor) -> Extraction
```

It returns an Extraction, whose claims list is the output and whose defect count is the number of claims dropped, because a defect count with nowhere to live is a defect count that disappears. The signature is also the enforcement: no session id, no transcript, no evidence log, no repository path. `tests/test_isolation.py` asserts that the request body built for the API contains the report, as numbered sentences, and the vocabulary, and nothing else that appears in the fixture session.

**The sentence contract.** The report goes to the model cut into numbered sentences, one a line, `[1]`, `[2]` and so on, by `ledger.sentences`, the same cut `tools/annotate.py` asks the annotator about. The model answers with numbers, and each claim's span is the sentence its number names, taken from the report by the client. So a span is always text the report holds: the model never copies one. Until 18 October 2026 the model copied each span itself, and every model measured dropped markup or quotation marks often enough that phase 1's "no non-verbatim span" could not be met (DECISIONS).

**Output schema**, validated before anything else touches it:

```json
{"claims": [
  {"sentence": 2,
   "type": "suite_passed",
   "referents": ["pytest"]},
  {"sentence": 4,
   "type": "file_changed",
   "referents": ["src/parser.py"]}
]}
```

- `sentence` is a whole number. One the report does not have is dropped and counted as an extraction defect, never guessed at. Several claims may name one sentence, which is how a sentence holding two assertions is typed twice.
- `type` is one of the five. Anything else fails validation.
- `referents` are the names the sentence itself gives: a command, a suite name, a path. The extractor never resolves them against the repository, because it cannot see it.
- An empty `claims` list is a valid answer and means the report asserts nothing checkable. It is not a failure.

**Call.** A direct HTTPS request with `temperature` 0 to the address `[extractor]` names, carrying the key from the variable it names, in the header it names. OpenRouter serves an Anthropic-shaped `/api/v1/messages` that takes the same request schema; both `x-api-key` and `Authorization: Bearer` were verified to work there on 20 September 2026. The prompt lives in its own file and travels as a declared version plus a hash of its text, so an edit without a version bump cannot inherit an earlier measurement. Claude Code's built-in `prompt` hook type is the tempting alternative, but its output is shaped for hook decisions, not for returning a claim list, so the client stays ours.

**The route is pinned, and moving the pin is dated.** One provider, `allow_fallbacks` false, `data_collection` deny, `require_parameters` true. The model is `deepseek/deepseek-v4.1-flash` — the exact id, since several V4 Flash variants differ in price and provider count — served by `morph`. It replaced `z-ai/glm-5.3-flash` on 21 September 2026 for one measured reason: glm spends about 5,000 tokens reasoning on a 442-character report and took 49.8 seconds against a 15-second turn budget, where this route answers in 6 to 9 seconds with thinking off. Before that, the glm pin moved from `phala/fp8` to `baseten/fp8` when phala twice returned HTTP 400 to a body that had worked. A pin may be moved before a corpus is measured and not during one: the provider is part of what the figure means. What answered travels with every claim, beside the model, the address and the prompt version (R-45).

**`openai/gpt-5.6-luna` was measured and refused**, also on 20 September 2026. It was the fastest and cheapest of the three, with no defects, but it returned three different answers across seven runs, twice with a fourth claim. GPT-5.x accepts neither `temperature` nor `top_p`, so its sampling cannot be pinned, and an unrepeatable extractor cannot carry a recall figure.

**The answer's shape is enforced, not asked for.** `output_config` with a JSON schema works on that endpoint and is what `answer_shape = "json_schema"` sends. It ends code fences and stray keys at the source, and it cannot know how many sentences the report has, which is why validation still runs and the defect count still means something. `answer_shape = "prefill"` is the fallback for a route that enforces nothing: the assistant turn is opened with a brace so the model continues an object. That fallback does not work here — this route returns a whole object and ignores the prefill — and a route that ignores it makes the turn `UNKNOWN` rather than being quietly repaired.

**Thinking is off, and that was checked in the reply.** This model reasons by default, and the `reasoning` parameter does not stop it: the switch is the provider's own chat template, `extra_body.chat_template_kwargs.enable_thinking`. Accepted is not honoured — DeepInfra, Fireworks, Together and AtlasCloud all took the switch and reasoned anyway, at 2,000 to 5,100 thinking tokens and 25 to 67 seconds, while morph returned a reply carrying no thinking block at all. The two providers that declare fp8 are among those that ignore it. So the setting is verified by what comes back, never by the status code, and the client passes over any non-text block regardless.

**Failure modes**, all of them ending the same way:

| Condition | Result |
| --- | --- |
| HTTP error, timeout, no key | turn marked `UNKNOWN` |
| The pinned provider rate-limits or drops the call | one retry, then `UNKNOWN`. With fallbacks off there is nowhere else to go, which is the price of a measurable route |
| The reply is cut off at the token ceiling | turn marked `UNKNOWN`: a truncated claim list read as complete is how coverage goes blind |
| Output not valid JSON, or schema invalid | turn marked `UNKNOWN` |
| Report longer than `max_report_chars` | turn marked `UNKNOWN`, not truncated |
| Valid output, zero claims | normal turn, appendix says so |

An `UNKNOWN` turn writes its reason to `errors.log`, shows one line in the appendix, and still records the report for the corpus. It never silently reads as a clean turn (I-9).

## Join, verdicts and coverage

No model runs here. Given a claim and the log, the verdict is a lookup, and the lookup table is one dict in `join.py`.

**Matching, per type**

| Type | Evidence sought | Match rule |
| --- | --- | --- |
| `suite_passed` | the last `check` record whose `check_id` the claim's referents resolve to | the referent is matched against check ids, their invocations and the aliases the config declares, and one that names something but resolves to nothing stays unsupported; only a claim naming no suite at all falls back, and only when the session used exactly one |
| `command_run` | the last record whose `command` matches | first token equal, and every further token the claim names present in the recorded command |
| `file_changed` | the last `mutation` record for that path | path normalised to project-relative, case-sensitive, symlinks resolved |
| `judgment`, `intent` | none | always `NOT_CHECKABLE` |

**The last matching record, for all three checkable types**, in log order — not
the best one. A claim in this turn's report is about the state the work is in
now, and the most recent record is what says what that is. Searching for any
successful record instead would verify "I updated the parser" against a write
that a later write undid, and "the migration ran" against the first of two
attempts.

The consequence is worth stating because it reads as a bug until it is
explained: **a file written `ok` and then written `failed` is `UNSUPPORTED`, not
`VERIFIED`.** The last record says the write failed, a failed write changed
nothing, and nothing is what the claim is then supported by. The same holds for
a check that passed and was then re-run into a failure — `CONTRADICTED`, on the
strength of the second run. Evidence does not accumulate; it is superseded.

**Freshness.** At join time, expand the check's `scope` globs and `stat` them on disk. The claim is fresh when the check's `ts_end` is later than the newest mtime among those files, and when no mutation record for a file it covers sits later in the log than the check itself. Both tests are needed because the harness stamps a hook when the call returns, not when it started. In a measured session a suite that began 2.7 seconds before an edit was recorded 461 milliseconds after it, so the timestamp test alone would have called it fresh and verified a suite that no longer passed. Subtracting duration\_ms does not rescue it either, since the harness does not measure the command end to end. The log-order test catches what the agent did, the mtime test what happened outside it, and both can only add STALE, never remove it. Reading the filesystem also covers a file written by a Bash command which, leaving no `files` entry, would have left a passing suite looking current. Files outside the check's scope cannot make it stale, and `command_run` and `file_changed` carry no freshness test. The scan reads the working tree as a person would see it: `.git` is skipped, so a `git add` cannot stale a check scoped `**/*`; the ledger's own directory is skipped, so writing the log cannot stale one either; and everything git ignores is dropped, in one batched `git check-ignore` rather than a call per file. Where there is no git, nothing is ignored.

**Verdict table**

| Type | Evidence | Outcome | Fresh | Verdict |
| --- | --- | --- | --- | --- |
| `suite_passed` | found | `ok` | yes | `VERIFIED` |
| `suite_passed` | found | `ok` | no | `STALE` |
| `suite_passed` | found | `failed` | any | `CONTRADICTED` |
| `suite_passed` | found | `unknown` | any | `UNKNOWN` |
| `suite_passed` | none | — | — | `UNSUPPORTED` |
| `command_run` | found | `ok` or `failed` | — | `VERIFIED`, with the outcome in its scope |
| `command_run` | found | `unknown` | — | `UNKNOWN` |
| `command_run` | none | — | — | `UNSUPPORTED` |
| `file_changed` | found | `ok` | — | `VERIFIED` |
| `file_changed` | found | `failed` or `unknown` | — | `UNSUPPORTED` |
| `file_changed` | none | — | — | `UNSUPPORTED` |
| any | — | — | — | `UNKNOWN` when the pipeline failed, the config changed, or `errors.log` has an entry for this session |

A `command_run` claim is about a command having run, so a failing run still verifies it and the failure travels in the scope. A `file_changed` claim is about the file being different, so a failed write verifies nothing.

Every `VERIFIED` carries its scope: the command, the outcome and the timestamp (I-4). A `command_run` verified against a failed run reads as ran, failed — which is accurate, and is why that row does not produce `CONTRADICTED`.

**Coverage.** A mutation whose outcome is `failed` wrote nothing and is not consequential; one whose outcome is `unknown` may have written, so it is listed (R-22). After the join, take every `mutation` record of the turn that is not a failure, every `check` record that failed, and every command at a tier above the default — `git push` and `rm -rf` are in the sample config precisely so they show up here. Drop those a `file_changed` or `command_run` claim already names, and list what remains as `UNREPORTED` with its tier. `LOW`-tier actions are counted but not listed individually. This is what stops a bare "done" from passing (I-7).

## Appendix format

The appendix is one line unless something needs saying. A ledger nobody reads is the failure mode this design is most likely to die of.

**Collapsed**, when every claim is `VERIFIED` or `NOT_CHECKABLE` and nothing consequential went unmentioned:

```text
claim-ledger · 4 verified, 2 unchecked · 2 checks seen · nothing unreported
```

**Expanded**, in this order, severity first:

```text
claim-ledger

CONTRADICTED
  "the tests pass"
  pytest -q failed at 2026-09-19T14:32:07.880Z

STALE
  "the suite is green"
  pytest -q ok at 2026-09-19T14:30:02.100Z; src/engine.py was modified at
  2026-09-19T14:35:12.004Z, after it ran

UNSUPPORTED
  "I ran the migration script"
  no matching command in this session

UNREPORTED
  migrations/0007_add_index.sql (HUMAN)

0 verified, 0 unchecked · 3 checks seen · 1 LOW-tier action not listed
```

**Corrected 23 September 2026, when the renderer was built.** The example above
said `exited 1` and gave bare clock times. Neither was reachable: the exit code
is deliberately not in the log, because the harness's error string is not a
stable format and parsing it is how a `CONTRADICTED` goes wrong, and the
timestamps are the full UTC ones the log and the mtimes share, since a scope
that drops the date cannot be compared against anything. The scope line is
`join`'s own text, printed as it wrote it and never reformatted (I-4). An
`EXTRACTION DEFECTS` group follows `UNREPORTED` when the model pointed at a
sentence the report does not have: a dropped claim is a claim that went
unjudged, and collapsing over one would hide the rate phase 1 exists to
measure.

- Entries are grouped by verdict, `CONTRADICTED` always first and alone at the head (R-29).
- A span longer than 120 characters is elided in the middle; the calibration log keeps it whole.
- `NOT_CHECKABLE` claims are counted, never listed. Listing opinions back to their author is noise.
- The whole thing is capped at 10,000 characters. On overflow, entries are dropped from the least severe upward and the last line says how many.
- The appendix goes to the user through `systemMessage`, and never into the model's context. Feeding it back would teach the agent what the ledger catches, which is the Goodhart failure the requirements name.

## Corpus capture

Phase 0 collects the material phase 1 needs. The fifty annotated reports of A-12 cannot be written from imagination, and the only honest source is real turns recorded while nothing else is running.

- From phase 0 onwards, every turn writes `reports/<session>-<n>.md`: the report text, the session id, the turn id, a per-session sequence number under the name turn\_number, and the slice of the evidence log for that turn.
- Capture is on by default and switched off by one config key, since a report may carry material the user does not want on disk.
- Annotation is by hand into `corpus/annotations.jsonl`, one object per report: the spans, their types, and the annotator's initials and date.
- The corpus is frozen before the first measurement, and any change to it is dated in place rather than applied silently.

```json
{"report": "abc123-7",
 "annotated": "2026-10-02",
 "by": "SP",
 "claims": [{"span": "the tests pass", "type": "suite_passed"}]}
```

Recall is measured per claim, on checkable types only, and the misses are listed one by one. An average over fifty reports hides exactly the case worth seeing: the claim the extractor never noticed. Since the extractor answers by sentence, a claim is matched by its sentence and its type: an annotated claim is found when the extractor typed the sentence holding it the same way.

A route whose answers vary from call to call has a different recall on every pass, so each candidate runs the corpus three times. Each pass's recall and spurious share are reported beside its share of `UNKNOWN` turns, and a candidate is judged by its worst pass: a miss that one pass makes is a miss, not a third of one. Beside them goes the share of checkable claims whose referents the join could match at all, by type (`usable` in `tools/measure_route.py`): a path relative to the project, a command whose first word runs, a suite the configuration declares. Recall does not see referents, and a claim that names nothing a log could hold stays `UNSUPPORTED` whatever the log says.

## Test plan

The suite makes no network call and no model call. Every test runs from a fixture session: an evidence log plus a report text, both plain files.

**Doubles.** The extractor client is replaced at the HTTP boundary, not at the function boundary, so schema validation, retry and parsing all run in the test. Responses come from recorded real outputs kept beside the fixtures, so the replay is a run that actually happened.

**Acceptance criteria as tests**

| Test | Covers | Fixture |
| --- | --- | --- |
| `test_join_stale` | A-1 | passing check, then a mutation inside its scope |
| `test_join_contradicted` | A-2 | check record whose outcome is failed |
| `test_not_checkable` | A-3, A-6 | report that declines to claim, and a judgment |
| `test_join_verified` | A-4 | mutation record matching the claimed path |
| `test_coverage_silence` | A-5 | three mutations, report says "done" |
| `test_pipeline_unknown` | A-7 | double returns invalid JSON, and a timeout |
| `test_install` | A-8 | deny rule present for the config file |
| `test_appendix_collapsed` | A-11 | everything verified, nothing unreported |
| `test_unsupported_command` | A-10 | claim naming a command absent from the log |

Added at step 8, when the pipeline had somewhere to run:

| Test | Covers |
| --- | --- |
| `tests/test_appendix.py` | the collapsed line, severity order, the 10,000 character cap, span elision |
| `tests/test_budget.py` | the turn's wall clock, and that an abandoned stage does not hold the process open |
| `tests/test_calibration.py` | R-34's rows and R-35's annotation appended without rewriting |
| `test_turn.PipelineTest` | the recorded answer from the route in use, driven all the way to an appendix |
| `test_turn.UnknownTurnTest` | every condition that makes a turn `UNKNOWN`, and that each one still captures |
| `test_turn.BudgetTest` | R-43: running out of budget reports rather than skipping, and is quick about it |

**Invariant tests**, which matter more than the scenarios:

- `test_isolation`: the extractor request body contains the report and the vocabulary, and none of the fixture's paths, commands or session ids.
- `test_no_upgrade`: for every fixture, no claim reaches `VERIFIED` without a matching record. Property-based over generated logs, not one example.
- `test_never_blocks`: the Stop handler never exits 2 in this phase.
- `test_record_fields`: no environment variable and no file content appears in any written record.

**Discipline.** A failing snapshot is never fixed by updating the expected value. Find what changed, and if the change is legitimate, date it in the spec. The suite runs on a pre-commit hook and in CI, and neither writes to `.claude/claim-ledger/`.

## Build order

Eight steps, each with a condition that decides whether it is done. Steps 1 to 4 are phase 0 and ship on their own.

| # | Step | Done when |
| --- | --- | --- |
| 1 | config loader and schema, with the sample `claim-ledger.toml` | an invalid config fails with the offending key named |
| 2 | recorder handler and log writer | synthetic hook inputs produce the exact records the fixtures expect |
| 3 | install: the two recorder registrations, deny rule, gitignore line. Stop joins at step 5 as a capture-only handler, and the pipeline moves into it at step 8 | a real session writes a log, and `test_install` passes |
| 4 | **phase 0 exit check** | **done**, date not recorded. A hand-written session, run by the user, compared line by line: 16 tool calls, 16 records, one to one |
| 5 | corpus capture | reports land with their evidence slice; capture switches off by config |
| 6 | extractor client, schema, doubles | recorded responses replay end to end without network |
| 7 | join, verdict table, coverage | the acceptance and invariant tests pass |
| 8 | appendix renderer and Stop wiring | **done, 23 September 2026.** An induced failure prints the `UNKNOWN` line: measured against a stalled endpoint, the hook rendered `claim-ledger · UNKNOWN · ExtractError: the model call passed its 12.0s deadline · 0 checks seen`, exited 0 by itself at 12.1s, and left 7.9s before the harness's kill. A real session printing the collapsed line waits on a key in the session environment |

Step 4 is blocking and worth its own session. If the log misses calls, every verdict built on it is uninterpretable, and no amount of work on the extractor would reveal it — the ledger would simply report fewer claims than it should, quietly.

After step 8, phase 1 runs for real while the corpus fills. The recall threshold gets written down before the corpus is measured, not after.

## Where the rest is written

`REQUIREMENTS.md` states what the system must do; this document states how.
`docs/DECISIONS.md` holds what neither records: decisions that exist only as
code, and the routes that were measured and rejected, with their dates.
`docs/provider-measurements.md` holds the numbers behind the extractor pin.

## Traps

Each of these looks like a reasonable improvement and breaks an invariant without failing anything.

- **Giving the extractor more context.** Passing the transcript or the tool results would raise recall and destroy I-1: the labeller would be reading the same evidence it is supposed to be checked against.
- **Treating a missing record as success.** An absent entry means the system does not know, which is `UNSUPPORTED`. Anything that turns silence into `VERIFIED` inverts the whole design.
- **Putting globs back into `[checks]`.** It will be tempting the first time a real invocation fails to match. A missed run costs a verification; a pattern that also matches `pytest --version` manufactures one.
- **Trusting the deny rule to protect the config.** It stops `Edit`, not a script. The hash check is the actual mechanism, and removing it because the deny rule "already covers it" reopens I-8.
- **Parsing the exit code out of the error string.** The reference says the format is not stable and that some failures omit it. `outcome` comes from the event, never from the text.
- **Inferring configuration.** Detecting the test command from the repository, or guessing which paths are consequential, moves the consequence table back inside the model's reach (I-8).
- **Feeding the appendix back to the agent.** It reads as helpful and teaches the agent which claims get caught, which is Goodhart by construction.
- **Repairing extractor output.** A sentence number the report does not have is a defect to count, not a number to guess, as a span not in the report was while the model copied spans. Fixing either hides the error rate that phase 1 exists to measure.
- **Blocking "just for contradictions".** That is phase 2, and it is gated on evidence that the extractor works. Shipping it early costs the clean base rate, which can only be collected once.
- **Updating a snapshot to green.** The expected number changes only after the cause is understood and dated.
- **Silent inertness.** A mistyped hook path fails non-blocking, so the session simply runs without a ledger. `test_install` and a visible line on the first turn of a session are what catch it.

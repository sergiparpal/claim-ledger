# Handover — 23 September 2026

For a session that has read REQUIREMENTS.md, SPEC.md and CLAUDE.md. Facts as
of this date; nothing here is a plan the user has approved.

## Where the build stands

Steps 1–7 of the build order are built: config, recorder and evidence log,
install, corpus capture, extractor client, join and coverage. Step 8 (appendix
renderer, Stop wiring) is not started.

- `python3 -m unittest discover` from the repo root: **176 tests, exit 0**, on
  Python 3.12.3, 3.13.14 and 3.14.6 and through `.githooks/pre-commit`.
- Step 4, the phase-0 exit check, was done by the user by hand and passed: 16
  tool calls, 16 records, one to one.
- **Nothing is wired into the Stop handler but capture.** `turn.py` writes
  `reports/<session>-<n>.md` and advances the turn counter. A test asserts it
  imports none of `extract`, `schema`, `join`, `coverage`.
- The extraction route is live and measured: `deepseek/deepseek-v4.1-flash`
  through OpenRouter's `/api/v1/messages`, provider `morph`, answer shape
  enforced by `output_config`, `temperature` 0, thinking off through
  `extra_body.chat_template_kwargs.enable_thinking`. 14 runs: 13 inside the
  12s deadline, median 3.8s, always the same three claims, no defects,
  $0.000085 a report.
- **The corpus does not exist.** One captured report is committed, in
  `tests/fixtures/sessions/real-v2/`, and the 442-character report the
  extractor fixtures were taken from is embedded in `tests/test_extract.py` as
  `CAPTURED_REPORT`. There is no `corpus/annotations.jsonl` and no recall
  figure.
- `OPENROUTER_API_KEY` is **not** in the Claude Code session environment. It is
  exported at line 131 of `~/.bashrc`; commands that need it load that one line
  (`eval "$(grep -E '^[[:space:]]*export[[:space:]]+OPENROUTER_API_KEY=' ~/.bashrc)"`).
- Nothing is committed: the repository has no commits.

**Do first:** run the suite to confirm the environment, then read "What I would
have done next" below and agree it with the user before changing the route,
the prompt or anything the corpus will be measured against.

## Decisions not written in the documents

1. **A record carries `turn_id` and `turn_number`.** `turn_id` is the harness's
   prompt id or `null`; `turn_number` is the per-session count, always present.
   `RECORD_VERSION` is 2 and logs written under 1 are refused loudly, so two
   shapes cannot both claim to be version 1.
2. **`evidence.read` returns `Entry(position, record, raw)`.** Position is the
   file position and the only ordering that survives (R-3). Never order records
   by `ts_end`; that is what step 4 caught.
3. **When git would commit the state directory, the recorder and the Stop
   handler write nothing at all** — not even `errors.log`, which would itself
   be committable — and return a `systemMessage` instead. Stderr on exit 0 goes
   only to the debug log, so it would have been a silent refusal.
4. **`tiers.default` must be exactly `"REVIEW"`** (R-26 read literally), and
   **`gate.enabled` must be `false`** (R-30): a config that claims a gate v1
   does not have is refused rather than ignored.
5. **`LOW` applies only when one LOW entry covers every part of an action**,
   while `HUMAN` matches any part. The spec states the HUMAN half only.
6. **Globs match the whole project-relative path**: `*.md` is root-only,
   `**/*.md` is any depth. A glob that cannot mean what it looks like is
   rejected, never read literally.
7. **Check matching sees the command as issued**: no wrapper or environment
   stripping, so `timeout 60 pytest` and `PYTHONPATH=src pytest` are not
   checks. Missing a run costs a verification; matching the wrong one invents
   one.
8. **The join uses the last matching record for every claim type.** The spec
   says "last" only for `suite_passed`. Consequence: a path written `ok` and
   then written `failed` reads as `UNSUPPORTED`.
9. **`extract.py` never opens a project file.** Settings are passed in;
   `config` is imported only under `TYPE_CHECKING`, so the module cannot call
   `config.load` at runtime. That is I-1 made structural.
10. **Nothing repairs a model's answer.** No fence stripping, no span tidying.
    An answer the client cannot read is `UNKNOWN`; a span that is not verbatim
    is a counted defect.
11. **`errors.log` is JSON lines**: `ts`, `component`, `session`, `turn_id`,
    `turn_number`, `error` (first line, capped at 500 characters).
12. **Stored commands**: first line only, cut at `log.max_command_chars`, with
    the value of each leading `NAME=value` replaced by `<redacted>`.
13. **Tests are checked by mutation.** Every session, the new code is broken
    one way at a time in a scratch copy and the suite must fail for each. Three
    mutants have survived so far and each one exposed a missing test.

Every number behind the rejections below, and behind the current pin, is in
`docs/provider-measurements.md` with its date and conditions. That file is what
decides the next pin when `morph` fails the way `phala` did; it cannot be
re-derived from the repository, and it goes stale.

## Tried and rejected — do not re-run these

- **`openai/gpt-5.6-luna`** (21 September). Fastest and cheapest, no defects,
  but GPT-5.x refuses `temperature` and `top_p`: with `require_parameters` on,
  sending either returns **404 from routing** before the model. Sampling cannot
  be pinned, and it gave three different answers across seven runs. Reasoning
  effort `"none"` is accepted there and still emits `redacted_thinking`.
- **`z-ai/glm-5.3-flash`.** Correct and stable, but ~5,000 thinking tokens and
  49.8s against a 15s turn budget. Its recording is kept as
  `openrouter-glm-5.3-flash.json` because it is the only one carrying a
  thinking block.
- **The assistant prefill on this route.** OpenRouter returns a whole object
  and ignores the prefill, so the brace the client adds makes `{{`.
  `answer_shape = "prefill"` stays for a route that honours it.
- **`phala/fp8`.** Returned HTTP 400 twice to a body that had worked; the pin
  moved to `baseten/fp8` (20 September) and then to `morph` with the model.
- **Providers that ignore `enable_thinking`**: DeepInfra, Fireworks, Together,
  AtlasCloud — including both that declare fp8. Only `morph` honoured it. The
  top-level `chat_template_kwargs` shape is ignored too. `novita/fp8` 404s
  under `require_parameters`.
- **The Claude Code CLI as an extraction transport** (used in step 6 before a
  key existed). Its recordings are the `cli-no-prefill-haiku*.json` fixtures.

## Open questions and gaps

- No corpus, so no recall. The threshold is declared and must not move.
- One run in fourteen missed the deadline: `UNKNOWN` turns will happen.
- `morph`'s quantization is undeclared, and the fp8 providers ignore the
  thinking switch. 18 of 22 providers are untested.
- Stability is measured on one 442-character report.
- **I-5 is implemented nowhere.** Nothing aggregates several claims in one
  sentence to the most severe verdict.
- The freshness scan walks the whole tree per check; untested on a large repo.
- Subagent tool calls are recorded like the main thread's; no `agent_id` is
  stored. Bash-written files leave no `files` entry. Cancelled and denied calls
  leave no record at all.
- Python 3.11 has never run, CI has never run (no remote), Windows paths have
  never been exercised.

## What I would have done next

1. Confirm the suite passes; change nothing about the route.
2. Fill the corpus: real sessions with capture on, `claude --plugin-dir <plugin>`
   from an installed sandbox, towards the 50 reports A-11 asks for.
3. Write `corpus/annotations.jsonl` by hand, then a recall harness that reports
   recall on checkable claims, the spurious rate, any non-verbatim span, and
   the `UNKNOWN` share beside it.
4. Only then step 8, the appendix and Stop wiring.

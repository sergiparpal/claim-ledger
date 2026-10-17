# Decisions — claim-ledger

The reasons that exist nowhere else.

A decision whose reason is already in a docstring, in `SPEC.md` or in
`REQUIREMENTS.md` is not repeated here: two copies of a reason is how one of
them comes to be wrong, and this file is the one nobody would notice had gone
stale. What belongs here is the decision a maintainer could undo without any
test failing, because the reason for it was never written down.

Build status is not here. `SPEC.md` § Build order says what is built,
`README.md` says what the plugin does and what it does not do yet, and
`OPERATING.md` says how to run it.

**Entries leave when their reason finds a home.** On 23 September 2026 the join
taking the last matching record, and the `LOW` half of the tier rule, both moved
into `SPEC.md`: they are behaviour someone can reason backwards from, which
makes them specification rather than folklore. An entry disappearing from here
is usually that, not a decision reversed.

**On the dates.** They are when the decision was written down, not always when
it was taken. Entries carried over from the handover this file replaces are
dated 23 September 2026; the build they came out of ran from 19 to 23 September
and finer dates are not recoverable from anything left behind.

## Decisions that exist only as code

### The refusal writes nothing at all, not even `errors.log` — 23 September 2026

While git would commit `.claude/claim-ledger/`, the recorder and the Stop
handler write no file of any kind and return a `systemMessage` instead.

The tempting repair is to at least log the refusal. `errors.log` lives in the
directory being refused, so writing it is the thing being refused. Stderr is no
better: on a hook that exits 0 it reaches only the debug log, which makes the
refusal silent, which is how a ledger ends up installed and inert.

### Tests are checked by mutation, every session — 23 September 2026

New code is broken one way at a time in a scratch copy, and the suite must fail
for each break. A mutant that survives is a missing test, not a curiosity.

This is the practice that keeps the suite from being decoration, and it is
written nowhere in the test plan. Eight mutants have survived so far — three
before 23 September 2026, five on it — and every one of them was a test that
did not exist. The five: coverage reading the whole session rather than the
turn, the model call ignoring what the budget had left, an unparseable
`errors.log` line being skipped, the config baseline never being seeded, and a
failing suite being reported as a pass.

## Tried, measured and rejected — do not re-run these

Every number behind these, and behind the current pin, is in
`docs/provider-measurements.md` with its date and conditions. That file is what
decides the next pin when `morph` fails the way `phala` did. It cannot be
re-derived from the repository and it goes stale.

### `openai/gpt-5.6-luna` — refused 21 September 2026

The fastest and cheapest of the three, with no defects, and unusable anyway.
GPT-5.x accepts neither `temperature` nor `top_p`: with `require_parameters` on,
sending either returns **404 from routing** before the model is reached. Sampling
that cannot be pinned gave three different answers across seven runs, twice with
a fourth claim. An extractor that varies cannot carry a recall figure.

Reasoning effort `"none"` is accepted there and still emits `redacted_thinking`.

### `z-ai/glm-5.3-flash` — replaced 21 September 2026

Correct and stable, and too slow to exist inside a turn: about 5,000 thinking
tokens on a 442-character report, 49.8 seconds against a 15-second budget.
Thinking cannot be switched off from this endpoint — `reasoning: {"enabled":
false}` is accepted and ignored.

Its recording is kept as `openrouter-glm-5.3-flash.json`, because it is the only
one in the fixtures that carries a thinking block, and the client's handling of
one would otherwise be untested.

### The assistant prefill, on this route — 20–21 September 2026

OpenRouter returns a whole object and ignores a prefilled assistant turn, so the
opening brace the client adds makes `{{`. `answer_shape = "prefill"` stays in
the loader for a route that honours it; on this one the answer shape is enforced
with `output_config` instead. The exact day is not recorded.

### `phala/fp8` — 20 September 2026

Returned HTTP 400 twice to a body that had worked minutes earlier. The pin moved
to `baseten/fp8`, and then to `morph` when the model changed. This is the failure
the provider-measurements table exists to answer quickly.

### The providers that accept `enable_thinking` and ignore it — 21 September 2026

DeepInfra, Fireworks, Together and AtlasCloud all took the switch and reasoned
anyway, at 2,000 to 5,100 thinking tokens and 25 to 67 seconds. Both providers
that declare fp8 are among them. Only `morph` returned a reply with no thinking
block at all, and `morph`'s quantization is undeclared — that is the price of
the switch working.

The top-level `chat_template_kwargs` shape, rather than under `extra_body`, is
ignored too. `novita/fp8` 404s under `require_parameters`.

**The rule this gives**: a parameter accepted is not a parameter honoured. Verify
against the reply, never against the status code.

### The Claude Code CLI as an extraction transport — 20 September 2026

Used in build step 6, before an API key existed on this machine. The CLI cannot
prefill an assistant turn, so its answers are whole objects from a route the
client no longer uses. Its recordings are the `cli-no-prefill-haiku*.json`
fixtures, kept as recordings rather than edited into the shape now sent: the
tests assert what the client does with them today, which is refuse them.

## Measured, and still open

### The alias table is a measurement target — 23 September 2026

The first live end-to-end turn: the report said "I updated src/parser.py and the
tests pass", the evidence log held a passing `python-suite` run, and the suite
claim came back `UNSUPPORTED`. The extractor returned the referent `tests`;
`[checks.aliases]` declares `"the tests"` and not bare `"tests"`, so the referent
named something, resolved to nothing, and stayed unsupported.

That is the rule working. It refused to fall back to the only check in the
session, which is exactly the fallback that manufactures a false `VERIFIED`.

But it makes the alias table an instrument rather than a convenience, and it is
not one that should be tuned from single observations. Collect what real reports
actually say during the corpus phase, then widen it once, deliberately. The file
is the user's (I-8).

### A command claim links only when the report names the command — 6 October 2026

The first audited turn in distiller, from the desktop app: the report said "Hice
el commit `2cbb88c` en una rama nueva, `spec-slice-1`, …", the evidence log held
`git switch -c spec-slice-1 && git add docs/SPEC.md && git commit …`, ok, in the
same turn, and the commit is in the repository. The claim came back
`UNSUPPORTED`. The extractor typed it `command_run` with the referents
`2cbb88c`, `spec-slice-1` and `main`, which is what its prompt asks for: the
names the sentence gives, never resolved.

`names_command` links a referent to a recorded command only when its first token
is the command's first token and every further token is in the command. A hash
or a branch is never a command's first token, and "hice el commit" names no
command at all. So a true claim about a command, worded the way reports word
them, stays unsupported.

That is the rule erring in the right direction (I-2): resolving "the commit" to
whichever git command happened to run is how a claim about one command gets
verified against another. Recall will not show it, since the claim was found
and typed right; it shows in the verdicts, as `UNSUPPORTED` on a command the
log holds. Like the alias table, count it during the corpus phase rather than
tune it from one turn. `join.py` is frozen, so any change there is the user's.

A later turn showed the same rule missing compound commands: "usé pytest
9.1.1, pytest‑cov 7.1.0 y coverage 7.16.2 …" against more than twenty recorded
commands that ran pytest after a `cd … &&`, inside a `for` loop or behind a
variable assignment. None begins with `pytest`, and a report seldom names a
command by its first word as it was typed.

On 17 October 2026 a report named a command exactly as it was typed, and the
rule missed it all the same. "`make protected REF=main`: sin salida." came back
`UNSUPPORTED` against `make protected REF=main; echo "protected exit=$?"; make
verify …`, ok, in the same turn. The recorded line is split on whitespace, so
its third token is `REF=main;`, with the operator attached, and `REF=main` is
not among its tokens. The verdict errs the safe way, but not for the rule's
reason: nothing in that claim was ambiguous.

### A claim about a tool the log does not record is always unsupported — 6 October 2026

A later turn in distiller said "Por eso comparé `HEAD` con el commit anterior,
`7cd4728`, para que el análisis cubra el commit de la spec." It was true: the
agent had called semantic-diff-weaver's MCP tool on `7cd4728` and `HEAD`. It came
back `UNSUPPORTED`, "no matching command in this session", and nothing else was
possible: the recorder's matcher is `Bash|Edit|Write|NotebookEdit` (SPEC § Hook
wiring), so an MCP call, like a Read, a WebFetch or any other tool, leaves no
record for a claim to join.

That is I-2 working too: a claim nothing in the log can support is
`UNSUPPORTED`, never a guess. But it is a different gap from the entry above.
There the record existed and the referents did not reach it; here there is no
record, and no wording of the claim would change that. How often it happens
depends on the tools a session has loaded, so a session with MCP servers shows
more true claims as `UNSUPPORTED` than one without.

Widening the matcher would record those calls, but `command_run` joins on a
command line and an MCP call has none. What such a record would hold, and what
a claim would have to name to reach it, is open. Count these during the corpus
phase, apart from the referent misses above, before deciding anything.

### A sentence can be typed as a file change it does not claim — 7 October 2026

A turn in distiller ended "Está en la rama local `spike/junit-coverage-contexts`
(commit `b96de07`, sin push), y `docs/SPEC.md` no se ha tocado." The extractor
typed the sentence `file_changed`, with `docs/SPEC.md` among its referents, and
the join found no write of that file in the session: `UNSUPPORTED`, "no record
of that file being written". It read as the agent claiming an edit it never
made. The sentence claimed the opposite, and the log agreed with it.

The vocabulary has no type for "I did not change X", and the prompt sends a
sentence that fits none of the checkable types to `judgment` or `intent`. So
this is a typing error by the extractor, and the measurement will count it as
one: the annotation guide says a claim that something was not done is
`judgment`. The prompt and the vocabulary are frozen; this is measured, not
fixed.

It matters beyond the noise. `file_changed` is joined against the whole
session's log, not the turn's slice: had `docs/SPEC.md` been written in an
earlier turn of the session, the same sentence would have come back `VERIFIED`,
verifying the opposite of what it says. That is the false `VERIFIED` the
prompt's "never guess upward" exists to prevent, so the corpus should show how
often a negation reaches a checkable type.

The same day a sentence with no negation and no file in it reached
`file_changed` too: "`f8edf74` es ahora `879625e`, en
`spec/junit-coverage-spike`.", about a commit the turn had rewritten with `git
commit --amend`. Its referents were the two hashes and the branch; a branch
named like a path is the likely trigger. It came back `UNSUPPORTED` only because
nothing was written at a path with one of those names. By the guide's rules it
is `judgment`: it names no file, and no command either.

The false `VERIFIED` this entry warns about had already happened, the day
before it was written, and gone unnoticed. A report on 6 October 2026 said
"Hice los cuatro cambios en [docs/SPEC.md](docs/SPEC.md). No toqué el Bet, los
no-objetivos ni los 8 `<TO FILL>`, y no he hecho commit." The extractor gave the
second sentence a claim of its own, typed `file_changed`, with `docs/SPEC.md` as
its referent, carried over from the sentence before. Every clause of it denies
an action, and it came back `VERIFIED` on the strength of the write the first
sentence claimed. On 17 October 2026 it happened again: "No he tocado nada
más.", closing a bullet headed `docs/SPEC.md`, typed and given its referent the
same way, came back `VERIFIED` against that turn's write of the SPEC. That one
was true, since the commit the turn made, `715e123`, adds four signatures to
the SPEC and nothing else; whether the first was true was not checked. Either
way the verdict could not tell: the log shows that a file was written, never
what was left alone, so a negation that reaches `file_changed` comes back
`VERIFIED` whenever its file was written at all.

Neither showed in the appendix, which counts `VERIFIED` claims and never lists
them; both were found by reading `claims.jsonl`. So were five more sentences
that claim a change and add "no he hecho commit" or "sin commit", a second
assertion the extractor left in the same span, `VERIFIED` on the strength of
the first.

### A file claim links only when it names the recorded path — 7 October 2026

A turn in distiller said "Contiene las dos tandas de cambios del SPEC (14 líneas
añadidas …) y no queda nada pendiente en el árbol de trabajo." `docs/SPEC.md`
had been edited ten times earlier in the session, and the commit the turn
amended holds that change. The extractor returned the referent `SPEC`, as the
sentence names it, and the claim came back `UNSUPPORTED`, "no record of that
file being written". Whether the sentence is a file claim at all, or a
description of the commit, is the annotator's call; the link failed either way.

`names_path` links a referent to a write only when it equals the recorded path,
project-relative and whole: `docs/SPEC.md` is reached by `docs/SPEC.md` and by
nothing else, not `SPEC.md` and not `SPEC`. Reports name files the way people
talk about them, and the log holds paths. This is the alias table's problem
again, for files rather than checks.

The direction is the same one: resolving "the SPEC" to whichever written file
looks like it is how a claim about one file gets verified against another, and
a match on the file name alone would join `README.md` to every README in a
repository. Count it during the corpus phase with the other referent misses;
`join.py` is frozen.

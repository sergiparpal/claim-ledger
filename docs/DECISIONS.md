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

### A claim is verified when any one of its referents is — 17 October 2026

A report in distiller said "`make protected REF=main` y `make verify` salen con
código 0." The extractor typed it `command_run` with both commands as its
referents, the log held one line that ran them both, `make protected REF=main;
echo "protected exit=$?"; make verify …`, ok, and the claim came back
`VERIFIED`. Further down, the same report said "`make protected REF=main`: sin
salida.", with that referent alone, and it came back `UNSUPPORTED`, for the
reason given under the command entry above. So the first claim was verified on
`make verify` alone.

`names_command` and `names_path` link a claim to a record when any one of its
referents reaches it, and `_suite` does the same in its own terms: a referent
that resolves to no check is dropped as long as another one resolves. The rule
in the module's docstring, that a referent which names something and resolves
to nothing is `UNSUPPORTED`, holds only for a claim with one referent. With two,
one found and one not, the claim takes the stronger verdict, and I-2 resolves
every ambiguity to the weaker.

It is not rare. Up to 17 October 2026, 20 `command_run` and `file_changed`
claims in distiller named two referents or more. Six came back `VERIFIED`, and
each of the six had a referent that the record which verified it does not hold;
in five of them that referent reaches nothing in the log at all. "El commit solo
incluye `docs/SPEC.md`, el árbol de trabajo queda limpio y `main` sigue en
`7cd4728`." was verified by a write of `docs/SPEC.md`, with `main` and `7cd4728`
reaching nothing. In the `make` case the other half was true, since both
commands are on the line that was found, but nothing in the join checked that.

No test pins it, either way. The property test in `test_join` gives each claim
zero referents or one, and a mutant that requires every referent to reach the
same record passes the whole suite, 321 tests on Python 3.12, on 17 October
2026. Requiring it is not free: all six claims would have come back
`UNSUPPORTED`, the true `make` claim among them, because the extractor's
referents include hashes, branches and identifiers that no record holds. Which
way to pin it is the user's; `join.py` is frozen.

A seventh came that afternoon, at 13:16 UTC, in another session: the same two
`make` targets as referents, verified against `make verify 2>&1 | grep …; echo
…` alone. `make protected REF=main` had run three times in that session, each
time as `make protected REF=main; echo …`, so the `;` described under the
command entry kept it from linking there too. Of the 21 claims with two
referents or more up to 18 October 2026, all 7 that came back `VERIFIED` rest on
part of what they name. `tools/daily_use.py verdicts` lists them.

### A write through Bash is invisible to file claims and to coverage — 17 October 2026

A report in distiller said "nueva D-004 con el contexto, lo elegido, lo
rechazado (…) y las consecuencias.", under a bullet headed `docs/DECISIONS.md`.
The extractor typed it `file_changed` with that exact path, and it came back
`UNSUPPORTED`, "no record of that file being written". The log held `cat >>
docs/DECISIONS.md <<'EOF'`, ok, in the same turn, and the commit the turn made,
`715e123`, holds the new entry.

The recorder takes `files` from the input of Edit, Write and NotebookEdit. A
Bash call that is not a check is recorded as `kind: other`, with its command
line cut at the first newline (R-7) and no `files` at all, and `names_path`
reads only mutation records. So no wording of a file claim reaches a write made
through the shell. It is the unrecorded-tool case above, except that here the
record exists.

The README lists the missing `files` entry as a known gap and says freshness is
unaffected, which is true: freshness reads mtimes from disk. Coverage is
affected. R-22 counts a file mutation as consequential, but coverage finds
mutations in mutation records, so a write through Bash at the default tier is
never listed as `UNREPORTED`. A report that says only "done" after a turn that
wrote only through the shell has nothing listed against it, and I-7 holds only
to its letter, since the log shows no mutation it left unmentioned.

That turn wrote through Bash four times: the `cat >>` above, a `sed -i` loop
renumbering `TASKS.md`, and two `python3 -` heredocs that rewrote it. One of
those wrote the note behind "Lo he anotado en la pregunta, citando K1 y K4.",
which came back `UNSUPPORTED` for this reason as well as for naming no file.
Which files a shell command wrote cannot be read from its command line, so this
is open. Count it during the corpus phase, apart from the referent misses.

### One turn in four passes the deadline — 17 October 2026

The route was measured at thirteen runs in fourteen inside the 12-second
deadline (`provider-measurements.md`), and README and OPERATING repeated the
figure until 17 October 2026. Daily use has been worse. Of the 49 turns
distiller captured from 6 to 17 October 2026, four ended on HTTP 401 and one on
a report over `max_report_chars`. Of the 44 left, whose call either answered or
ran out of time, 11 passed the deadline: 2 of the 22 captured before 10 October,
and 9 of the 22 since.

The times are the Stop hook's `durationMs`, which Claude Code writes into the
session transcript: the whole pipeline, not the call alone, and the only record
of latency there is, since the client writes down neither the usage nor whether
a thinking block came back. The turns that answered took a median of 2.9
seconds before 10 October and 6.9 since.

Report length does not explain it. Reports of 1,000 and 1,658 characters passed
the deadline on 17 October, and one of 9,164 answered in 3.1 seconds. The
measured runs moved too, from 6.1–8.6 seconds on 21 September to a median of
3.8 on 23 September. The route's speed changes from day to day, and nothing
recorded says why.

It matters beyond the turns it costs. Recall is to be reported beside the share
of turns that came back `UNKNOWN`, and `tools/extract_report.py`, the one tool
that runs the extractor outside a turn, takes the same deadline from the
project's `claim-ledger.toml`. What a longer deadline would buy is not known,
because a call abandoned at 12 seconds leaves no trace of how long it would have
taken. The deadline is in the frozen `[extractor]` table, the three timeouts
must stay strictly ordered, and the hook's own lives in `hooks/hooks.json`,
which an installed copy picks up only after a version bump and an update.
Moving any of them is the user's.

Later the same day the route was measured with a 150-second deadline
(`provider-measurements.md`). In a seven-minute window every call finished
inside 15 seconds and 93 of 96 inside 12, at about 0.65 seconds plus 4.7
milliseconds per output token: the deadline caps the size of an answer, at about
2,400 tokens for 12 seconds, and the length of the report hardly matters. The 11
reports whose turns had passed it answered in 0.5 to 9.6 seconds. The same
report can get answers of very different sizes (the next entry), and the hook
has also taken 7.8 seconds over two claims, so those turns met a longer answer,
a slower hour, or both. The window caught no slow hour, and the tail in one is
still unmeasured.

That evening a watcher caught one (`provider-measurements.md`). From 16:57 to
17:10 UTC the same calls on real reports took a median of 4.7 seconds and up to
38.6: 81% finished inside 12 seconds, 93% inside 20, all of them inside 45.
Neither this machine's network nor OpenRouter's front was slower; the time went
after the first byte, at the provider, which delivered about 89 tokens a second
instead of 184, so each output token cost about 10 milliseconds instead of 5.
The deadline still caps the size of an answer, but at a slow hour the cap is
less than half as large, about 1,000 tokens for 12 seconds: the largest answer
of that run, 2,943 tokens, took 38.6 seconds.

### The route no longer gives the same answer twice — 17 October 2026

The route was frozen on a measurement that included its repeatability: the
thirteen runs that answered on 21 and 23 September gave the same three claims
every time. On 17 October 2026 the same request, sent by the hook's own code
with a long deadline, went out twice for each of the 48 reports distiller had
captured. Eight got the same answer both times. The claim count differed in 31,
by a factor of two or more in 13, and 21 of the 107 answers were empty lists,
among them reports whose other run found 18, 26, 33 and 45 claims. The fixed
report of the September runs gave three distinct answers in eleven, none the one
recorded then, and two of its answers read that day name `git add`, `commit` and
`push` as referents of a sentence that names none of them. The numbers and their
conditions are in `provider-measurements.md`.

`temperature` 0 is sent and accepted, and the answers vary anyway. Whether the
provider ignores it, or runs the model in a way that breaks near-ties
differently from one call to the next, cannot be seen from here: the reply names
the provider and says nothing about how it ran. The thinking switch still holds;
none of the 107 replies carried a reasoning token.

Two consequences run against the design. A recall figure taken from one run of
an extractor that varies like this describes that run, which is why
`openai/gpt-5.6-luna` was refused. And an empty list is a valid answer (R-12),
so a turn whose answer comes back empty does not read `UNKNOWN`: it reads as a
report that claims nothing, and only coverage, listing the turn's writes as
unreported, hints otherwise.

It may be recent. The first 33 turns the hook answered, from 6 to 17 October,
include no empty answer. The 34th was one, and it came inside the window above:
turn 1 of distiller session `6cc8dfdd`, at 11:55 UTC on 17 October 2026. Its
report, 2,438 characters, names the commit it made, the one file it changed and
two `make` targets that exited 0. The hook took 523 milliseconds, where every
turn that came back with claims took 1.9 seconds or more, and it printed
`0 verified, 0 unchecked` with no extraction defect, so the model returned an
empty list: `schema.validate` turns every item of an answer into a claim, a
defect or an `UNKNOWN` turn. Above that line it listed `TASKS.md (REVIEW)`
three times as `UNREPORTED`, once for each Edit the turn made to it. That is
I-7 working, not a second fault: coverage excuses a write only when a claim
names its path, and with no claims it excused nothing. It does put on the
report an omission that was the extractor's. In a turn with nothing
consequential to list, one that only read or wrote only through Bash (the entry
above), the same answer prints the collapsed line,
`0 verified, 0 unchecked · … · nothing unreported`, and nothing on it tells
that turn apart from one whose report claimed nothing.

The 35th was one too, and it came after the window: turn 2 of the same session,
at 12:46 UTC, 48 minutes after the window closed. Its report, 3,484 characters,
again names the commit it made, the one file it changed and the two `make`
targets, and gives the full path of a script the agent wrote in its scratchpad,
outside the project. The hook took 776 milliseconds, printed no defect, and
listed ten `UNREPORTED` lines: nine edits of `TASKS.md` and the write of that
script. So the empty answers are not confined to the window. Counting the two
turns before them, which passed the deadline at 10:41 and 10:51 UTC, four
distiller turns in a row produced no claim. How often it happens, and whether
it lasts, still needs another window, ideally at a slow hour. The route is
frozen, so what to do about it is the user's.

An empty answer writes nothing to `claims.jsonl`, whose rows are one per claim
and one per defect, so the provider that gave it is recorded nowhere: R-45
carries the route on each claim. Both were found in the appendix Claude Code
writes into the session transcript, and that is the only place empty answers
can be counted from. Among the ledger's own files, a captured report with no
claim row and no `errors.log` entry is also what a hook killed after its capture
leaves behind.

The slow hour came that evening (`provider-measurements.md`), and the answers
varied as much at half the speed. From 16:57 to 17:10 UTC 23 of the 107 were
empty lists and only 6 of the 48 reports got the same answer twice; over the
day's four runs, 2 of the 48 got one answer every time. A report probed 57 times
between 12:22 and 16:57 UTC never came back empty, and gave 25 distinct answers.
So it lasted the afternoon, at either speed.

The hook met two more that day: turn 1 of session `6ffb997c` at 14:13 UTC and
turn 1 of `ed68cf55` at 20:05 UTC, each in under a second and a half. Of the 12
distiller turns of 17 October whose call answered or ran out of time, 4 came
back empty and 2 passed the deadline. `tools/daily_use.py latency` counts empty
answers from the transcripts, the one place they show.

### No suite claim can be verified in distiller — 17 October 2026

Turn 3 of distiller session `6cc8dfdd`, at 13:16 UTC, reported each step of
`make verify` by quoting its output, «16 files already formatted», «29 passed»
and «6 kept, 0 broken» among them, and the pre-commit hook of its commit by its
line, «Detect hardcoded secrets… Passed». Seven of those claims came back
`UNSUPPORTED`, "no run of that check in this session", and an eighth, that
`check_characters.py` printed nothing, "no matching command". All eight were
true. The outputs in the session transcript hold every quote and nothing from
`check_characters.py`, and `make verify` printed its own exit status, 0.

The first reason is the configuration. Distiller's `claim-ledger.toml` declares
no check: its `[checks]` says "None yet. distiller holds a design document and
no code", which was true when it was written on 5 October 2026. The Makefile
and the tests came on 12 October, and the file has not changed since. So every
`suite_passed` claim there lands `UNSUPPORTED` whatever it names, 13 of 13 up
to 17 October, and all 52 appendices distiller has printed say
`0 checks seen`: its session logs hold 835 records and not one check. R-29
prints that count even at zero because zero is worth seeing, and here it
accounted for all thirteen.

The second reason would remain with `make verify` declared. It ran eleven times
in distiller's logs and never on its own, always behind a pipe, a `;` or a
`&&`. In this turn it was
`make verify 2>&1 | grep -v …; echo "make verify exit: ${PIPESTATUS[0]}"`.
A command with a shell operator is never a check, and here that rule is what
keeps the verdict honest: the line exits with the status of `echo`, 0 whatever
make did, so the `ok` recorded for it says nothing about the suite. The agent
read make's status from the output; the ledger keeps no output (R-7). The
pre-commit claim has no route at all: the hook ran inside
`git add TASKS.md && git commit …`, which no configuration can make a check.

The tempting repair is to look for the quotes in the command's output instead
of requiring a run of the check, and it was proposed the same day. Two things
stop it. The log holds no output, by R-7, because output carries file contents
and secrets. And a substring is not an outcome: «0 errors» is inside
«10 errors», «29 passed» inside «1 failed, 29 passed», and «Passed» ends the
line of every pre-commit hook that passes, so a match would resolve an
ambiguity upward, against I-2. It is the error-string trap of SPEC § Traps,
moved to the output.

What would let such a claim verify is the user's. `[checks]` would need
`make verify` with its scope, and aliases from `pytest`, `pyright` and the rest
to it if a claim naming one tool is to reach that run. Such an alias says that
a passing `make verify` vouches for the tool, which is a fact about the
Makefile and not one the ledger may infer. And the run would have to be the
bare invocation, which is the agent's habit; changing it for the ledger's sake
would stop the corpus representing real use (ANNOTATING § While using the
plugin). A change to the file mid-session makes every later turn of that
session `UNKNOWN` (I-8), until the file is restored byte for byte; a new
session takes the changed file as its baseline.

At the user's request the check was declared the same day:
`verify = ["make verify"]`, scoped `**/*`, since the character check reads
every file git does not ignore and gitleaks reads the history, and with no
aliases yet. The bare run, and the aliases, are still open.

### Daily use left no hole in the evidence log — 18 October 2026

The phase-0 check of SPEC § Build order compared one hand-written session, 16
calls, with its log. On 18 October 2026 `tools/daily_use.py recording` made the
same comparison for all 21 sessions distiller had logged since 6 October: every
call the recorder's matcher covers that ran has its record, and every record has
its call.

Twenty-two covered calls have no record of their own, and none is a hole. Ten
were refused before they ran, six by the permission settings, two by
distiller's own PreToolUse hook, one by the auto-mode classifier and one by a
deny rule, and a refused call fires no hook (R-44). Twelve sit in the transcript
of session `94212a41`, which resumed `f89f6cd8` and repeats its calls; they are
recorded under `f89f6cd8`. None was cancelled.

No distiller session ran a subagent, so where a subagent's transcript is kept
was never seen; the tool reads any transcript in the session's folder, on the
assumption that it is there.

### A span is dropped when the extractor tidies it — 18 October 2026

On 17 October 2026 a distiller turn showed an extraction defect: a span ended
"`select`, `judge`." where the report has "`select`, `judge`».", so it was not
in the report, and it was dropped and listed under `EXTRACTION DEFECTS`, as
SPEC requires. The guess at the time was that the extractor mishandles Spanish
quotation marks.

The defects say otherwise. Up to 18 October 2026 the hook has dropped 8 spans,
in 7 of the 36 turns whose answer was not empty, and `tools/daily_use.py
defects` names what each one changed. Five dropped the `**` that closes a bold
label: `**La regla** (…` came back as `La regla (…`, starting after the opening
marker, as a reader sees the text, and losing the closing one inside it. One
dropped the closing guillemet above, one the full stop of «.», and one turned
"corrijo" into "correcciones". Meanwhile 51 kept spans hold a guillemet, and 14
a `**`, copied whole. What the defects share is the extractor tidying the text
it was told to copy, which its prompt forbids: "copy rather than tidy".

The tempting repair is to compare spans with the markup stripped, or loosely.
That is the repair SPEC § Traps rules out: it hides the rate phase 1 exists to
measure, and a loose match would pass "correcciones" for "corrijo", a word the
report does not hold.

It matters to phase 1, which tolerates no non-verbatim span (REQUIREMENTS §
Rollout phases), and the measurement runs of 17 October met more: a defect in
17 and in 12 of 107 answers (`provider-measurements.md`). The prompt is frozen,
so this is measured, not fixed, and a shortfall sends us to the misses, not to
the number.
